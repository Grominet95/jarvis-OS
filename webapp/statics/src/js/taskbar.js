function initTaskbar() {
    setIcon(document.querySelector('#btn-plugins .btn-icon'), 'plugins');
    setIcon(document.querySelector('#btn-devices .btn-icon'), 'devices');

    setIcon(document.querySelector('#mini-btn-1'), 'security');
    setIcon(document.querySelector('#mini-btn-2'), 'location');
    setIcon(document.querySelector('#mini-btn-3'), 'feedback');
    setIcon(document.querySelector('#mini-btn-4'), 'settings');
    setIcon(document.querySelector('#mini-btn-5'), 'more');

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

    const taskbarButtons = document.querySelectorAll('.taskbar-btn');
    taskbarButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            console.log('Taskbar button clicked:', btn.id);
        });
    });

    const miniButtons = document.querySelectorAll('.mini-btn');
    miniButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            console.log('Mini button clicked:', btn.id);
        });
    });

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
