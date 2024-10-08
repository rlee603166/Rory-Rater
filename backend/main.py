import os
from config import app, db
from model import Gif
from flask import Flask, request, jsonify, url_for, send_file, abort
from flask_cors import CORS, cross_origin
from sqlalchemy import and_
from moviepy.editor import VideoFileClip
import uuid

import tensorflow as tf
import tensorflow_hub as hub
import numpy as np
from helpers.movenet_helpers import _keypoints_and_edges_for_display
from helpers.vid_helpers import init_crop_region, determine_crop_region, run_inference
from helpers.data_processors import align_vids, center_pts, convert_to_json, delete_gifs, recursive_convert_to_list

CORS(app)

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
PROCESSED_FOLDER = os.path.join(os.getcwd(), 'processed')
PREDICTED_FOLDER = os.path.join(os.getcwd(), 'predicted')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['PREDICTED_FOLDER'] = PREDICTED_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(PREDICTED_FOLDER, exist_ok=True)

rory_process_id = '06008295-f58f-4725-9cb4-b950665c7fbc'

model_path = './movenet-tensorflow2-singlepose-thunder-v4'
model_name = 'movenet_thunder'

module = tf.saved_model.load(model_path)
input_size = 256

def movenet(input_image):
    model = module.signatures['serving_default']

    input_image = tf.cast(input_image, dtype=tf.int32)
    outputs = model(input_image)
    keypoints_with_scores = outputs['output_0'].numpy()
    return keypoints_with_scores

def predict(gif):
    num_frames, org_height, org_width, _ = gif.shape
    crop_region = init_crop_region(org_height, org_width)
    kps_edges = []
    
    for i in range(num_frames):
        kps_scores = run_inference(
            movenet,
            gif[i, :, :, :],
            crop_region,
            crop_size=[input_size, input_size]
        )
        kps_edges.append(_keypoints_and_edges_for_display(
            kps_scores,
            org_height,
            org_width
        ))
        crop_region = determine_crop_region(
            kps_scores, 
            org_height, 
            org_width
        )
    return kps_edges



@app.route("/")
def hello_world():
    return "Hello World!"


@app.route("/upload", methods=['GET', 'POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file found'}), 400
    videos = request.files.getlist('file')
    
    front_impact_time = request.form.get('front_impact_time')
    back_impact_time = request.form.get('back_impact_time')
    try:
        front_impact_time = float(front_impact_time) if front_impact_time else None
        back_impact_time = float(back_impact_time) if back_impact_time else None
    except ValueError:
        return jsonify({'error': 'Invalid impact time format'}), 400

    if len(videos) < 2:
        return jsonify({'error': 'Submit two videos!'}), 400
    if videos and videos[0].filename.endswith('.mp4'):
        delete_gifs()
        gifs = []
        for video in videos:
            path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
            video.save(path)

            gif_name = f'{os.path.splitext(video.filename)[0]}.gif'
            gif_path = os.path.join(app.config['PROCESSED_FOLDER'], gif_name)
            video = VideoFileClip(path)
            video.write_gif(gif_path)
            
            print("Video saved at:", path)
            print("GIF saved at:", gif_path)

            if os.path.exists(path):
                print("Video file exists.")
            if os.path.exists(gif_path):
                print("GIF file exists.")

            gifs.append(gif_name)
            
        
        Gif.query.filter(Gif.process_id != rory_process_id).delete()
        
        db.session.commit()    
        
        process_id = str(uuid.uuid4())
        
        front_path, back_path = os.path.join(app.config['PROCESSED_FOLDER'], gifs[0]), os.path.join(app.config['PROCESSED_FOLDER'], gifs[1])
        front = tf.io.read_file(front_path)
        front = tf.image.decode_gif(front)
        
        back = tf.io.read_file(back_path)
        back = tf.image.decode_gif(back)
        
        front_kps_edges = predict(front)
        back_kps_edges = predict(back)
        
        front_kps = center_pts(front_kps_edges)
        back_kps = center_pts(back_kps_edges)
        
        front_kps = recursive_convert_to_list(front_kps)
        back_kps = recursive_convert_to_list(back_kps)
        
        front_kps, back_kps, impact_frame = align_vids(front_kps, float(front_impact_time), back_kps, float(back_impact_time))
        assert len(front_kps) == len(back_kps)
        prediction = Gif(process_id=process_id, front_kps=front_kps, back_kps=back_kps)
        
        db.session.add(prediction)
        db.session.commit()

        print('process_id: ', process_id)
        return jsonify({'process_id': process_id})
    else:
        return jsonify({'error': 'Video not supported'}), 400
    
@app.route("/get/<process_id>", methods=['GET'])
def get(process_id):
    gif = Gif.query.filter_by(process_id=process_id).first()
    if gif:
        response_data = gif.to_json()
        
        return jsonify({ 'prediction': response_data })
    
    return jsonify({ 'error': 'GIF not found' }), 404

@app.route("/get-rory", methods=['GET'])
def get_rory():
    gif = Gif.query.filter_by(process_id=rory_process_id).first()
    if gif:
        response_data = gif.to_json()
        
        return jsonify({ 'prediction': response_data })
    
    return jsonify({ 'error': 'GIF not found' }), 404

@app.route("/gif/<filename>", methods=['GET', 'POST'])
def get_gif(filename):
    path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    return send_file(path, mimetype='image/gif')

@app.route("/predict/<gif_name>", methods=['GET'])
def handle_prediction(gif_name):
    gif_path = os.path.join(app.config['PROCESSED_FOLDER'], f'{gif_name}.gif')
    gif = tf.io.read_file(gif_path)
    gif = tf.image.decode_gif(gif)
    
    kps_edges = predict(gif)
    keypoints, edges = center_pts(kps_edges)
    json_kps = [convert_to_json(keypoint, edge) for keypoint, edge in zip(keypoints, edges)]
    
    return  jsonify(json_kps)

@app.route("/processed/<filename>", methods=['GET', 'POST'])
def get_predicted(filename):
    path = os.path.join(app.config['PREDICTED_FOLDER'], filename)

    return send_file(path, mimetype='image/gif')
    
    
#################################################
#                   Only for dev                #
#################################################

@app.route('/reload-rory', methods=['GET'])
def reload_rory():
    front_path, back_path = './processed/rory-front.gif', './processed/rory-back.gif'
    
    front = tf.io.read_file(front_path)
    front = tf.image.decode_gif(front)
    
    back = tf.io.read_file(back_path)
    back = tf.image.decode_gif(back)
    
    front_kps_edges = predict(front)
    back_kps_edges = predict(back)
    
    front_kps = center_pts(front_kps_edges)
    back_kps = center_pts(back_kps_edges)
    
    front_kps = recursive_convert_to_list(front_kps)
    back_kps = recursive_convert_to_list(back_kps)
    
    front_kps, back_kps, impact_frame = align_vids(front_kps, 0.3233107015842224, back_kps, 0.3233107015842224)
    assert len(front_kps) == len(back_kps)
    
    process_id = str(uuid.uuid4())
    
    prediction = Gif(process_id=process_id, front_kps=front_kps, back_kps=back_kps)
    
    db.session.add(prediction)
    db.session.commit()

    print('process_id: ', rory_process_id)
    return jsonify({'process_id': rory_process_id})
    

@app.route('/count', methods=['GET'])
def get_count():
    query = db.session.query(Gif)
    
    return jsonify({ 'database_count': query.count() })
    
@app.route('/clear-database', methods=['POST'])
def clear_database():
    if not app.config['DEBUG']:
        abort(403, description="Forbidden: This endpoint is only for development.")

    db.session.query(Gif).filter(Gif.process_id != rory_process_id).delete()
    db.session.commit()

    return jsonify({"message": "Database cleared and recreated!"})



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        
    app.run(debug=True)