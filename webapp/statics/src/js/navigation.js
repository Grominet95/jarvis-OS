const Navigation = {
    currentPage: 'home',

    init() {
        this.setupListeners();
        this.showPage('home');
    },

    setupListeners() {
        const appTitle = document.querySelector('.app-title');
        const pluginsBtn = document.getElementById('btn-plugins');
        const devicesBtn = document.getElementById('btn-devices');

        if (appTitle) {
            appTitle.style.cursor = 'pointer';
            appTitle.addEventListener('click', () => this.navigateTo('home'));
        }

        if (pluginsBtn) {
            pluginsBtn.addEventListener('click', () => this.navigateTo('plugins'));
        }

        if (devicesBtn) {
            devicesBtn.addEventListener('click', () => this.navigateTo('devices'));
        }
    },

    navigateTo(page) {
        if (this.currentPage === page) return;

        this.hidePage(this.currentPage);
        this.showPage(page);
        this.updateActiveButton(page);
        this.currentPage = page;
    },

    showPage(page) {
        const pageElement = document.getElementById(`page-${page}`);
        if (pageElement) {
            pageElement.style.display = 'flex';
            setTimeout(() => {
                pageElement.style.opacity = '1';
            }, 10);
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
        const buttons = document.querySelectorAll('.taskbar-btn');
        buttons.forEach(btn => {
            btn.classList.remove('active');
        });

        if (page === 'home') {
            return;
        } else if (page === 'plugins') {
            document.getElementById('btn-plugins')?.classList.add('active');
        } else if (page === 'devices') {
            document.getElementById('btn-devices')?.classList.add('active');
        }
    }
};
