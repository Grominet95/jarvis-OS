const Navigation = {
    currentPage: 'home',

    init() {
        this.setupListeners();
        this.showPage('home');
    },

    setupListeners() {
        const appTitle = document.querySelector('.app-title');
        const settingsBtn = document.getElementById('btn-settings');

        if (appTitle) {
            appTitle.style.cursor = 'pointer';
            appTitle.addEventListener('click', () => this.navigateTo('home'));
        }

        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                console.log('[NAV] Settings button clicked');
                this.navigateTo('settings');
            });
        } else {
            console.error('[NAV] Settings button not found!');
        }
    },

    navigateTo(page) {
        if (this.currentPage === page) return;

        const allPages = document.querySelectorAll('.page');
        allPages.forEach(p => {
            p.style.display = 'none';
            p.style.opacity = '0';
        });

        this.showPage(page);
        this.updateActiveButton(page);
        this.currentPage = page;
    },

    showPage(page) {
        const pageElement = document.getElementById(`page-${page}`);
        console.log(`[NAV] Showing page: ${page}`, pageElement);
        if (pageElement) {
            if (page === 'settings') {
                pageElement.style.display = 'block';
                pageElement.style.opacity = '1';
                console.log('[NAV] Initializing settings manager...');
                setTimeout(() => {
                    if (window.settingsManager) {
                        window.settingsManager.init();
                    } else {
                        console.error('[NAV] SettingsManager not available!');
                    }
                }, 50);
            } else {
                pageElement.style.display = 'flex';
                pageElement.style.opacity = '1';
            }
        } else {
            console.error(`[NAV] Page element not found: page-${page}`);
        }
    },

    hidePage(page) {
        const pageElement = document.getElementById(`page-${page}`);
        if (pageElement) {
            pageElement.style.opacity = '0';
            setTimeout(() => {
                pageElement.style.display = 'none';
            }, 200);
        }
    },

    updateActiveButton(page) {
        const buttons = document.querySelectorAll('.mini-btn');
        buttons.forEach(btn => {
            btn.classList.remove('active');
        });

        if (page === 'settings') {
            document.getElementById('btn-settings')?.classList.add('active');
        }
    }
};

window.Navigation = Navigation;
