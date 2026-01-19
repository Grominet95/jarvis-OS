function initVisualizer() {
    const visualizer = document.getElementById('visualizer');
    if (!visualizer) return;

    const leftSide = document.createElement('div');
    leftSide.className = 'visualizer-side left';
    for (let i = 0; i < 3; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        leftSide.appendChild(bar);
    }
    visualizer.appendChild(leftSide);

    const square = document.createElement('div');
    square.className = 'visualizer-square';
    visualizer.appendChild(square);

    const rightSide = document.createElement('div');
    rightSide.className = 'visualizer-side right';
    for (let i = 0; i < 3; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        rightSide.appendChild(bar);
    }
    visualizer.appendChild(rightSide);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initVisualizer);
} else {
    initVisualizer();
}
