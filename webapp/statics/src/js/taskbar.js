function initTaskbar() {
    setIcon(document.querySelector('#voice-mic-btn'), 'microphone');
    setIcon(document.querySelector('#btn-settings'), 'settings');

    setIcon(document.querySelector('.camera-placeholder'), 'camera');

    const hasCompletedOnboarding = localStorage.getItem('jarvis_onboarding_completed');
    if (hasCompletedOnboarding) {
        const appContainer = document.querySelector('.app-container');
        if (appContainer) {
            appContainer.classList.add('visible');
        }

        const userName = localStorage.getItem('jarvis_user_name');
        const userGreeting = document.getElementById('user-greeting');
        if (userName && userGreeting) {
            userGreeting.textContent = `Bonjour ${userName}`;
            setTimeout(() => {
                userGreeting.classList.add('visible');
            }, 300);
        }

        const chatContainer = document.getElementById('chat-container');
        if (chatContainer && chatContainer.children.length === 0) {
            const welcomeMessage = document.createElement('div');
            welcomeMessage.className = 'message system-message';
            welcomeMessage.innerHTML = `<p>Bonjour ${userName || 'Utilisateur'} ! Comment puis-je t'aider aujourd'hui ?</p>`;
            chatContainer.appendChild(welcomeMessage);
        }
    }

    const minimizeBtn = document.getElementById('minimize-btn');
    const closeBtn = document.getElementById('close-btn');
    const windowControls = document.querySelector('.window-controls');

    if (window.electronAPI) {
        if (minimizeBtn) {
            minimizeBtn.addEventListener('click', () => {
                window.electronAPI.minimizeWindow();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                window.electronAPI.closeWindow();
            });
        }
    } else {
        if (windowControls) {
            windowControls.style.display = 'none';
        }
    }


    const deactivateBtn = document.getElementById('deactivate-btn');
    if (deactivateBtn) {
        deactivateBtn.addEventListener('click', () => {
            console.log('Deactivate button clicked');
        });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTaskbar);
} else {
    initTaskbar();
}
