import { useEffect, useRef, useState } from "react";
import SwingView from "./SwingView";
import './styles/Playground.css'

import roryFront from './assets/rory-front.mp4'
import roryBack from './assets/rory-back.mp4'

function Playground({ setPlayground }) {

    const [RoryGifData, setRoryGifData] = useState([]);
    const [roryGifDuration, setRoryGifDuration] = useState(0);
    const [roryLoading, setRoryLoading] = useState(true);
    const [dimensions, setDimensions] = useState({
        width: window.innerWidth * 0.33,
        height: window.innerHeight * 0.9
    })

    let rory_url = 'http://127.0.0.1:5000/get-rory';


    useEffect(() => {
        fetchRory();
    }, []);

    const fetchRory = async () => {
        try {
            const rory_response = await fetch(`${rory_url}`);
            const rory_data = await rory_response.json();
            const rory_predictions = rory_data.prediction;
            setRoryGifData(rory_predictions);
            setRoryGifDuration(rory_predictions.back_kps.length - 1);
        } catch (error) {
            console.log(error);
        } finally {
            setRoryLoading(false);
            console.log(roryLoading);
        }
    }

    useEffect(() => {
        // Check if window is defined (only run in browser environment)
        if (typeof window !== 'undefined') {
            const handleResize = () => {
                setDimensions({
                    width: window.innerWidth * 0.3,
                    height: window.innerHeight * 0.95,
                });
            };
    
            // Add the event listener
            window.addEventListener('resize', handleResize);
    
            // Cleanup function to remove the event listener
            return () => {
                window.removeEventListener('resize', handleResize);
            };
        }
    }, []);

    const handleClick = () => {
        setPlayground(false)
    }
    

    return (
        <div className="play-container">
            <SwingView
                width={dimensions.width}
                height={dimensions.height}
                gifData={RoryGifData}
                videoFront={roryFront}
                videoBack={roryBack}
                isLoading={roryLoading}
                isLeft={false}
                gifDuration={roryGifDuration}
                difference={0}
                isPlayground={false}
            />
            <div className="controls">
                <button className="reupload" onClick={handleClick}>Back</button>
            </div>
        </div>
    );
}

export default Playground;