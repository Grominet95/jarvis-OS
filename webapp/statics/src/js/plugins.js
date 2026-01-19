const PluginsManager = {
    currentTab: 'installed',
    currentFilter: 'all',

    plugins: [
        {
            id: 'weather',
            name: 'Weather',
            version: '1.2.0',
            description: 'Plugin météo pour obtenir les prévisions et conditions actuelles en temps réel.',
            status: 'active',
            icon: 'plugins',
            category: 'utilities'
        },
        {
            id: 'calendar',
            name: 'Calendar',
            version: '2.1.3',
            description: 'Intégration calendrier pour gérer vos événements et rendez-vous avec synchronisation.',
            status: 'active',
            icon: 'plugins',
            category: 'productivity'
        }
    ],

    storePlugins: [
        {
            id: 'spotify',
            name: 'Spotify',
            version: '1.0.0',
            description: 'Contrôlez votre musique Spotify directement depuis J.A.R.V.I.S.',
            category: 'entertainment',
            icon: 'plugins',
            rating: 4.8,
            downloads: 1250,
            installed: false
        },
        {
            id: 'todo',
            name: 'Todo List',
            version: '1.5.2',
            description: 'Gestionnaire de tâches intelligent avec rappels et priorités.',
            category: 'productivity',
            icon: 'plugins',
            rating: 4.9,
            downloads: 3200,
            installed: false
        },
        {
            id: 'news',
            name: 'News Reader',
            version: '2.1.0',
            description: 'Lisez les dernières actualités de vos sources préférées.',
            category: 'utilities',
            icon: 'plugins',
            rating: 4.6,
            downloads: 890,
            installed: false
        },
        {
            id: 'translator',
            name: 'Translator',
            version: '1.8.1',
            description: 'Traduction en temps réel dans plus de 100 langues.',
            category: 'utilities',
            icon: 'plugins',
            rating: 4.7,
            downloads: 2100,
            installed: false
        },
        {
            id: 'calculator',
            name: 'Calculator',
            version: '1.3.0',
            description: 'Calculatrice avancée avec fonctions scientifiques et conversions.',
            category: 'utilities',
            icon: 'plugins',
            rating: 4.5,
            downloads: 1500,
            installed: false
        },
        {
            id: 'reminder',
            name: 'Reminder',
            version: '1.2.5',
            description: 'Système de rappels intelligent avec notifications personnalisées.',
            category: 'productivity',
            icon: 'plugins',
            rating: 4.8,
            downloads: 2800,
            installed: false
        },
        {
            id: 'youtube',
            name: 'YouTube',
            version: '1.1.0',
            description: 'Recherchez et lisez les descriptions de vidéos YouTube.',
            category: 'entertainment',
            icon: 'plugins',
            rating: 4.4,
            downloads: 1100,
            installed: false
        },
        {
            id: 'email',
            name: 'Email Manager',
            version: '2.0.0',
            description: 'Gérez vos emails avec lecture vocale et réponses rapides.',
            category: 'productivity',
            icon: 'plugins',
            rating: 4.9,
            downloads: 4500,
            installed: false
        },
        {
            id: 'weather-pro',
            name: 'Weather Pro',
            version: '2.0.0',
            description: 'Version avancée avec prévisions détaillées et alertes météo.',
            category: 'utilities',
            icon: 'plugins',
            rating: 4.7,
            downloads: 950,
            installed: false
        },
        {
            id: 'music',
            name: 'Music Player',
            version: '1.4.0',
            description: 'Lecteur de musique local avec contrôle vocal complet.',
            category: 'entertainment',
            icon: 'plugins',
            rating: 4.6,
            downloads: 1800,
            installed: false
        },
        {
            id: 'notes',
            name: 'Notes',
            version: '1.1.0',
            description: 'Prenez des notes vocales et textuelles avec synchronisation cloud.',
            category: 'productivity',
            icon: 'plugins',
            rating: 4.8,
            downloads: 2200,
            installed: false
        },
        {
            id: 'timer',
            name: 'Timer & Stopwatch',
            version: '1.0.5',
            description: 'Minuteur et chronomètre avec alertes personnalisables.',
            category: 'utilities',
            icon: 'plugins',
            rating: 4.5,
            downloads: 1300,
            installed: false
        }
    ],

    init() {
        this.setupTabs();
        this.setupFilters();
        this.setupSearch();
        this.renderPlugins();
        this.renderStore();
        this.updateCounts();

    },

    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                this.switchTab(tab);
            });
        });
    },

    setupFilters() {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const filter = btn.dataset.filter;
                this.setFilter(filter);
            });
        });
    },

    setupSearch() {
        const searchInput = document.getElementById('plugins-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterBySearch(e.target.value);
            });
        }
    },

    switchTab(tab) {
        this.currentTab = tab;

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tab}"]`)?.classList.add('active');

        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`tab-${tab}`)?.classList.add('active');
    },

    setFilter(filter) {
        this.currentFilter = filter;

        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-filter="${filter}"]`)?.classList.add('active');

        this.renderStore();
    },

    filterBySearch(query) {
        const lowerQuery = query.toLowerCase();
        const cards = document.querySelectorAll('.plugin-card');

        cards.forEach(card => {
            const name = card.querySelector('h3')?.textContent.toLowerCase() || '';
            const desc = card.querySelector('.plugin-description')?.textContent.toLowerCase() || '';

            if (name.includes(lowerQuery) || desc.includes(lowerQuery)) {
                card.style.display = '';
                card.style.animation = 'fadeInUp 0.3s ease';
            } else {
                card.style.display = 'none';
            }
        });
    },

    renderPlugins() {
        const grid = document.getElementById('plugins-grid');
        if (!grid) return;

        grid.innerHTML = '';

        this.plugins.forEach((plugin, index) => {
            const card = this.createPluginCard(plugin, false);
            card.style.animationDelay = `${index * 0.05}s`;
            grid.appendChild(card);
        });
    },

    renderStore() {
        const grid = document.getElementById('store-grid');
        if (!grid) return;

        grid.innerHTML = '';

        let filtered = this.storePlugins;

        if (this.currentFilter !== 'all') {
            filtered = filtered.filter(p => p.category === this.currentFilter);
        }

        filtered.forEach((plugin, index) => {
            const card = this.createStoreCard(plugin, index);
            grid.appendChild(card);
        });
    },

    equalizeCardHeights(gridId) {
        const grid = document.getElementById(gridId);
        if (!grid) return;

        const cards = Array.from(grid.children);
        if (cards.length === 0) return;

        const gridStyle = window.getComputedStyle(grid);
        const columnCount = gridStyle.gridTemplateColumns.split(' ').length;

        for (let i = 0; i < cards.length; i += columnCount) {
            const rowCards = cards.slice(i, i + columnCount);
            if (rowCards.length === 0) break;

            let maxHeight = 0;
            rowCards.forEach(card => {
                card.style.height = 'auto';
                maxHeight = Math.max(maxHeight, card.offsetHeight);
            });

            rowCards.forEach(card => {
                card.style.height = maxHeight + 'px';
            });
        }
    },

    createPluginCard(plugin, isStore = false) {
        const card = document.createElement('div');
        card.className = 'plugin-card';

        const iconElement = document.createElement('div');
        iconElement.className = 'plugin-icon';
        setIcon(iconElement, plugin.icon);

        const header = document.createElement('div');
        header.className = 'plugin-card-header';
        header.appendChild(iconElement);

        const info = document.createElement('div');
        info.className = 'plugin-info';
        info.innerHTML = `
            <h3>${plugin.name}</h3>
            <span class="plugin-version">v${plugin.version}</span>
        `;
        header.appendChild(info);

        const description = document.createElement('div');
        description.className = 'plugin-description';
        description.textContent = plugin.description;

        const footer = document.createElement('div');
        footer.className = 'plugin-footer';

        const status = document.createElement('div');
        status.className = `plugin-status ${plugin.status}`;
        status.innerHTML = `
            <span class="status-dot"></span>
            <span>${plugin.status === 'active' ? 'Actif' : 'Inactif'}</span>
        `;

        const actions = document.createElement('div');
        actions.className = 'plugin-actions';

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'plugin-btn primary';
        toggleBtn.textContent = plugin.status === 'active' ? 'Désactiver' : 'Activer';
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.togglePlugin(plugin.id);
        });

        const settingsBtn = document.createElement('button');
        settingsBtn.className = 'plugin-btn';
        settingsBtn.textContent = 'Paramètres';
        settingsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            console.log('Settings clicked for:', plugin.id);
        });

        actions.appendChild(toggleBtn);
        actions.appendChild(settingsBtn);

        footer.appendChild(status);
        footer.appendChild(actions);

        card.appendChild(header);
        card.appendChild(description);
        card.appendChild(footer);

        return card;
    },

    createStoreCard(plugin, index) {
        const card = document.createElement('div');
        card.className = 'plugin-card store-card';
        card.style.animationDelay = `${index * 0.05}s`;

        const iconElement = document.createElement('div');
        iconElement.className = 'plugin-icon';
        setIcon(iconElement, plugin.icon);

        const header = document.createElement('div');
        header.className = 'plugin-card-header';
        header.appendChild(iconElement);

        const info = document.createElement('div');
        info.className = 'plugin-info';
        info.innerHTML = `
            <h3>${plugin.name}</h3>
            <span class="plugin-version">v${plugin.version}</span>
            <div class="plugin-rating">
                <span class="star">★</span>
                <span>${plugin.rating}</span>
                <span style="margin-left: 8px; opacity: 0.6;">•</span>
                <span style="opacity: 0.6;">${plugin.downloads.toLocaleString()} téléchargements</span>
            </div>
        `;
        header.appendChild(info);

        const description = document.createElement('div');
        description.className = 'plugin-description';
        description.textContent = plugin.description;

        const footer = document.createElement('div');
        footer.className = 'plugin-footer';

        const actions = document.createElement('div');
        actions.className = 'plugin-actions';

        const installBtn = document.createElement('button');
        installBtn.className = 'plugin-btn install';
        installBtn.textContent = plugin.installed ? 'Installé' : 'Installer';
        installBtn.disabled = plugin.installed;
        installBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.installPlugin(plugin.id);
        });

        actions.appendChild(installBtn);

        footer.appendChild(actions);

        card.appendChild(header);
        card.appendChild(description);
        card.appendChild(footer);

        return card;
    },

    togglePlugin(pluginId) {
        const plugin = this.plugins.find(p => p.id === pluginId);
        if (plugin) {
            plugin.status = plugin.status === 'active' ? 'inactive' : 'active';
            this.renderPlugins();
            this.updateCounts();
        }
    },

    installPlugin(pluginId) {
        const storePlugin = this.storePlugins.find(p => p.id === pluginId);
        if (!storePlugin || storePlugin.installed) return;

        storePlugin.installed = true;

        const newPlugin = {
            id: storePlugin.id,
            name: storePlugin.name,
            version: storePlugin.version,
            description: storePlugin.description,
            status: 'active',
            icon: storePlugin.icon,
            category: storePlugin.category
        };

        this.plugins.push(newPlugin);

        this.renderStore();
        this.renderPlugins();
        this.updateCounts();
    },

    updateCounts() {
        const installedCount = this.plugins.length;
        const storeCount = this.storePlugins.length;

        const installedBadge = document.getElementById('installed-count');
        const storeBadge = document.getElementById('store-count');

        if (installedBadge) installedBadge.textContent = installedCount;
        if (storeBadge) storeBadge.textContent = storeCount;

        const pluginsCountEl = document.getElementById('plugins-count');
        if (pluginsCountEl) pluginsCountEl.textContent = installedCount;
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        Navigation.init();
        PluginsManager.init();
    });
} else {
    Navigation.init();
    PluginsManager.init();
}
