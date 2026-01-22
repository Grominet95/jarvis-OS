let siriWaveInstance = null;
let currentAmplitude = 0;
let isActive = false;
let container = null;

function initVisualizer() {
    const visualizer = document.getElementById('visualizer');
    if (!visualizer) {
        console.warn('[VISUALIZER] Visualizer element not found');
        return;
    }

    visualizer.innerHTML = '';
    
    container = document.createElement('div');
    container.id = 'siriwave-container';
    container.className = 'siriwave-container';
    visualizer.appendChild(container);

    function tryInit() {
        if (!window.SiriWave) {
            console.error('[VISUALIZER] SiriWave not available on window object');
            console.error('[VISUALIZER] Make sure siriwave.umd.js is loaded in index.html');
            return;
        }

        const SiriWave = window.SiriWave.default || window.SiriWave;
        console.log('[VISUALIZER] SiriWave found, type:', typeof SiriWave);
        
        if (typeof SiriWave !== 'function') {
            console.error('[VISUALIZER] SiriWave is not a function:', typeof SiriWave, SiriWave);
            return;
        }
        
        const width = visualizer.offsetWidth || 800;
        const height = visualizer.offsetHeight || 180;

        console.log('[VISUALIZER] Initializing SiriWave with dimensions:', width, height);

        try {
            siriWaveInstance = new SiriWave({
                container: container,
                width: width,
                height: height,
                style: 'ios',
                amplitude: isActive ? currentAmplitude : 0,
                speed: isActive ? 0.04 : 0.01,
                autostart: true,
                color: '#5BA3F5',
                cover: true,
            });
            console.log('[VISUALIZER] SiriWave initialized successfully');

            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    if (siriWaveInstance && container) {
                        const newWidth = visualizer.offsetWidth || 800;
                        const newHeight = visualizer.offsetHeight || 180;
                        siriWaveInstance.dispose();
                        siriWaveInstance = new SiriWave({
                            container: container,
                            width: newWidth,
                            height: newHeight,
                            style: 'ios',
                            amplitude: isActive ? currentAmplitude : 0,
                            speed: isActive ? 0.04 : 0.01,
                            autostart: true,
                            color: '#5BA3F5',
                            cover: true,
                        });
                    }
                }, 250);
            });
        } catch (error) {
            console.error('[VISUALIZER] Failed to initialize SiriWave:', error, error.stack);
        }
    }
    
    tryInit();
}

function updateVisualizerAmplitude(amplitude) {
    currentAmplitude = amplitude;
    isActive = amplitude > 0.1;
    
    if (siriWaveInstance) {
        const targetAmplitude = isActive ? Math.max(1, amplitude) : 0;
        try {
            siriWaveInstance.setAmplitude(targetAmplitude);
            siriWaveInstance.setSpeed(isActive ? 0.04 : 0.01);
        } catch (error) {
            console.error('[VISUALIZER] Error updating amplitude:', error);
        }
    } else {
        if (amplitude > 0) {
            console.warn('[VISUALIZER] SiriWave instance not available, amplitude:', amplitude);
        }
    }
}

window.updateVisualizerAmplitude = updateVisualizerAmplitude;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initVisualizer);
} else {
    initVisualizer();
}
