class SettingsManager {
    constructor() {
        this.audioDevices = {
            input: [],
            output: []
        };
        this.selectedDevices = {
            input: null,
            output: null
        };
        this.jarvisSettings = {
            voice: 'femme',
            language: 'en'
        };
        this.initialized = false;
        this.listenersSetup = false;
        this.currentCategory = 'audio';
    }

    async init() {
        console.log('[SETTINGS] Initializing SettingsManager...');
        if (!this.initialized) {
            this.setupEventListeners();
            this.initialized = true;
        }

        const audioIcon = document.querySelector('[data-icon="audio"]');
        const generalIcon = document.querySelector('[data-icon="general"]');
        const advancedIcon = document.querySelector('[data-icon="advanced"]');
        
        if (audioIcon && typeof setIcon === 'function') {
            setIcon(audioIcon, 'audio');
        }
        if (generalIcon && typeof setIcon === 'function') {
            setIcon(generalIcon, 'general');
        }
        if (advancedIcon && typeof setIcon === 'function') {
            setIcon(advancedIcon, 'advanced');
        }

        this.switchCategory(this.currentCategory);
        
        const inputSelect = document.getElementById('settings-audio-input');
        const outputSelect = document.getElementById('settings-audio-output');
        
        if (!inputSelect || !outputSelect) {
            console.error('[SETTINGS] Select elements not found, waiting...');
            setTimeout(() => this.init(), 100);
            return;
        }
        
        try {
            await this.loadAudioDevices();
            await this.loadSavedSettings();
            await this.loadJarvisSettings();
            await this.loadUserProfile();
            await this.loadApiKeys();
            this.render();
            this.renderJarvis();
            console.log('[SETTINGS] SettingsManager initialized, devices:', {
                input: this.audioDevices.input.length,
                output: this.audioDevices.output.length
            });
        } catch (error) {
            console.error('[SETTINGS] Init error:', error);
            this.showErrorMessage('Erreur lors de l\'initialisation: ' + error.message);
            this.render();
        }
    }

    async loadAudioDevices() {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                console.error('MediaDevices API not available');
                this.showErrorMessage('API MediaDevices non disponible');
                this.audioDevices.input = [{ deviceId: 'default', label: 'API non disponible', groupId: 'default' }];
                this.audioDevices.output = [{ deviceId: 'default', label: 'API non disponible', groupId: 'default' }];
                return;
            }

            let stream = null;
            let devices = [];
            
            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                devices = await navigator.mediaDevices.enumerateDevices();
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                }
            } catch (permError) {
                console.warn('Microphone permission not granted, trying to enumerate anyway:', permError);
                try {
                    devices = await navigator.mediaDevices.enumerateDevices();
                } catch (enumError) {
                    console.error('Failed to enumerate devices:', enumError);
                    throw enumError;
                }
            }

            const inputDevices = devices.filter(device => device.kind === 'audioinput');
            const outputDevices = devices.filter(device => device.kind === 'audiooutput');

            this.audioDevices.input = inputDevices.map((device, index) => ({
                deviceId: device.deviceId,
                label: device.label || `Microphone ${index + 1}`,
                groupId: device.groupId
            }));

            this.audioDevices.output = outputDevices.map((device, index) => ({
                deviceId: device.deviceId,
                label: device.label || `Haut-parleur ${index + 1}`,
                groupId: device.groupId
            }));

            if (this.audioDevices.input.length === 0) {
                this.audioDevices.input.push({
                    deviceId: 'default',
                    label: 'Microphone par défaut',
                    groupId: 'default'
                });
                this.selectedDevices.input = 'default';
            }

            if (this.audioDevices.output.length === 0) {
                this.audioDevices.output.push({
                    deviceId: 'default',
                    label: 'Haut-parleur par défaut',
                    groupId: 'default'
                });
                this.selectedDevices.output = 'default';
            }
            
            console.log('[SETTINGS] Loaded devices - Input:', this.audioDevices.input.length, 'Output:', this.audioDevices.output.length);
        } catch (error) {
            console.error('Error loading audio devices:', error);
            this.showErrorMessage('Erreur lors du chargement des périphériques: ' + error.message);
            this.audioDevices.input = [{ deviceId: 'default', label: 'Erreur de chargement', groupId: 'default' }];
            this.audioDevices.output = [{ deviceId: 'default', label: 'Erreur de chargement', groupId: 'default' }];
        }
    }

    async loadSavedSettings() {
        try {
            if (window.electronAPI && window.electronAPI.getSetting) {
                const savedInput = await window.electronAPI.getSetting('audioInputDevice');
                const savedOutput = await window.electronAPI.getSetting('audioOutputDevice');
                
                if (savedInput) {
                    this.selectedDevices.input = savedInput;
                } else if (this.audioDevices.input.length > 0) {
                    this.selectedDevices.input = this.audioDevices.input[0].deviceId;
                }

                if (savedOutput) {
                    this.selectedDevices.output = savedOutput;
                } else if (this.audioDevices.output.length > 0) {
                    this.selectedDevices.output = this.audioDevices.output[0].deviceId;
                }
            } else {
                if (this.audioDevices.input.length > 0) {
                    this.selectedDevices.input = this.audioDevices.input[0].deviceId;
                }
                if (this.audioDevices.output.length > 0) {
                    this.selectedDevices.output = this.audioDevices.output[0].deviceId;
                }
            }
        } catch (error) {
            console.error('Error loading saved settings:', error);
        }
    }

    async loadJarvisSettings() {
        try {
            if (window.electronAPI && window.electronAPI.getSetting) {
                const savedVoice = await window.electronAPI.getSetting('jarvis_voice');
                const savedLanguage = await window.electronAPI.getSetting('jarvis_language');
                if (savedVoice) this.jarvisSettings.voice = savedVoice;
                if (savedLanguage) this.jarvisSettings.language = savedLanguage;
            } else {
                const v = localStorage.getItem('jarvis_voice');
                const l = localStorage.getItem('jarvis_language');
                if (v) this.jarvisSettings.voice = v;
                if (l) this.jarvisSettings.language = l;
            }
        } catch (error) {
            console.error('Error loading Jarvis settings:', error);
        }
    }

    async saveJarvisSettings() {
        try {
            const voiceSelect = document.getElementById('settings-jarvis-voice');
            const languageSelect = document.getElementById('settings-jarvis-language');
            const voice = voiceSelect ? voiceSelect.value : 'femme';
            const language = languageSelect ? languageSelect.value : 'en';
            this.jarvisSettings.voice = voice;
            this.jarvisSettings.language = language;

            if (window.electronAPI && window.electronAPI.setSetting) {
                await window.electronAPI.setSetting('jarvis_voice', voice);
                await window.electronAPI.setSetting('jarvis_language', language);
            } else {
                localStorage.setItem('jarvis_voice', voice);
                localStorage.setItem('jarvis_language', language);
            }

            this.showJarvisMessage('Voix et langue enregistrées', true);
        } catch (error) {
            console.error('Error saving Jarvis settings:', error);
            this.showJarvisMessage('Erreur lors de la sauvegarde', false);
        }
    }

    showJarvisMessage(message, success) {
        const el = document.getElementById('settings-jarvis-message');
        if (!el) return;
        el.textContent = message;
        el.className = 'settings-message ' + (success ? 'settings-message-success' : 'settings-message-error');
        el.style.display = 'block';
        setTimeout(() => { el.style.display = 'none'; }, 3000);
    }

    async saveSettings() {
        try {
            if (window.electronAPI && window.electronAPI.setSetting) {
                await window.electronAPI.setSetting('audioInputDevice', this.selectedDevices.input);
                await window.electronAPI.setSetting('audioOutputDevice', this.selectedDevices.output);
            } else {
                localStorage.setItem('audioInputDevice', this.selectedDevices.input);
                localStorage.setItem('audioOutputDevice', this.selectedDevices.output);
            }

            if (window.voiceManager) {
                await window.voiceManager.applyAudioSettings(this.selectedDevices);
            }

            this.showSuccessMessage('Paramètres audio sauvegardés');
        } catch (error) {
            console.error('Error saving settings:', error);
            this.showErrorMessage('Erreur lors de la sauvegarde');
        }
    }

    setupEventListeners() {
        if (this.listenersSetup) {
            return;
        }
        
        const inputSelect = document.getElementById('settings-audio-input');
        const outputSelect = document.getElementById('settings-audio-output');
        const saveBtn = document.getElementById('settings-save-btn');
        const refreshBtn = document.getElementById('settings-refresh-btn');
        const backBtn = document.getElementById('settings-back-btn');

        if (inputSelect) {
            inputSelect.addEventListener('change', (e) => {
                this.selectedDevices.input = e.target.value;
            });
        }

        if (outputSelect) {
            outputSelect.addEventListener('change', (e) => {
                this.selectedDevices.output = e.target.value;
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                this.saveSettings();
            });
        }

        const saveApiBtn = document.getElementById('settings-save-api-btn');
        if (saveApiBtn) {
            saveApiBtn.addEventListener('click', () => {
                this.saveApiKeys();
            });
        }

        const saveJarvisBtn = document.getElementById('settings-save-jarvis-btn');
        if (saveJarvisBtn) {
            saveJarvisBtn.addEventListener('click', () => {
                this.saveJarvisSettings();
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                this.showSuccessMessage('Actualisation des périphériques...');
                await this.loadAudioDevices();
                this.render();
                this.showSuccessMessage('Périphériques actualisés');
            });
        }

        if (backBtn) {
            backBtn.addEventListener('click', () => {
                if (window.Navigation) {
                    window.Navigation.navigateTo('home');
                }
            });
        }

        const navItems = document.querySelectorAll('.settings-nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                const category = e.currentTarget.getAttribute('data-category');
                this.switchCategory(category);
            });
        });
        
        this.listenersSetup = true;
    }

    switchCategory(category) {
        this.currentCategory = category;

        const navItems = document.querySelectorAll('.settings-nav-item');
        navItems.forEach(item => {
            if (item.getAttribute('data-category') === category) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        const categories = document.querySelectorAll('.settings-category');
        categories.forEach(cat => {
            if (cat.id === `settings-category-${category}`) {
                cat.style.display = 'block';
            } else {
                cat.style.display = 'none';
            }
        });
    }

    render() {
        console.log('[SETTINGS] Rendering devices...', {
            input: this.audioDevices.input.length,
            output: this.audioDevices.output.length,
            selected: this.selectedDevices
        });
        
        const inputSelect = document.getElementById('settings-audio-input');
        const outputSelect = document.getElementById('settings-audio-output');

        if (!inputSelect || !outputSelect) {
            console.error('[SETTINGS] Select elements not found!', { inputSelect, outputSelect });
            setTimeout(() => this.render(), 100);
            return;
        }

        inputSelect.innerHTML = '';
        if (this.audioDevices.input.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Aucun microphone trouvé';
            inputSelect.appendChild(option);
        } else {
            this.audioDevices.input.forEach(device => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label;
                if (device.deviceId === this.selectedDevices.input || (!this.selectedDevices.input && device.deviceId === this.audioDevices.input[0].deviceId)) {
                    option.selected = true;
                    this.selectedDevices.input = device.deviceId;
                }
                inputSelect.appendChild(option);
            });
        }

        outputSelect.innerHTML = '';
        if (this.audioDevices.output.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Aucun haut-parleur trouvé';
            outputSelect.appendChild(option);
        } else {
            this.audioDevices.output.forEach(device => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label;
                if (device.deviceId === this.selectedDevices.output || (!this.selectedDevices.output && device.deviceId === this.audioDevices.output[0].deviceId)) {
                    option.selected = true;
                    this.selectedDevices.output = device.deviceId;
                }
                outputSelect.appendChild(option);
            });
        }
        
        console.log('[SETTINGS] Render complete - Input options:', inputSelect.options.length, 'Output options:', outputSelect.options.length);
    }

    renderJarvis() {
        const voiceSelect = document.getElementById('settings-jarvis-voice');
        const languageSelect = document.getElementById('settings-jarvis-language');
        if (voiceSelect) voiceSelect.value = this.jarvisSettings.voice || 'femme';
        if (languageSelect) languageSelect.value = this.jarvisSettings.language || 'en';
    }

    showSuccessMessage(message) {
        const messageEl = document.getElementById('settings-message');
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.className = 'settings-message settings-message-success';
            messageEl.style.display = 'block';
            setTimeout(() => {
                messageEl.style.display = 'none';
            }, 3000);
        }
    }

    showErrorMessage(message) {
        const messageEl = document.getElementById('settings-message');
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.className = 'settings-message settings-message-error';
            messageEl.style.display = 'block';
            setTimeout(() => {
                messageEl.style.display = 'none';
            }, 3000);
        }
    }

    getSelectedDevices() {
        return { ...this.selectedDevices };
    }

    async loadUserProfile() {
        try {
            if (window.electronAPI && window.electronAPI.getUserProfile) {
                const profile = await window.electronAPI.getUserProfile();
                const firstNameInput = document.getElementById('settings-first-name');
                const birthDateInput = document.getElementById('settings-birth-date');
                const countryInput = document.getElementById('settings-country');
                const cityInput = document.getElementById('settings-city');

                if (firstNameInput && profile.first_name) firstNameInput.value = profile.first_name;
                if (birthDateInput && profile.birth_date) birthDateInput.value = profile.birth_date;
                if (countryInput && profile.country) countryInput.value = profile.country;
                if (cityInput && profile.city) cityInput.value = profile.city;
            }
        } catch (error) {
            console.error('Error loading user profile:', error);
        }
    }

    async saveUserProfile() {
        try {
            if (window.electronAPI && window.electronAPI.updateUserProfile) {
                const profile = {
                    first_name: document.getElementById('settings-first-name')?.value || '',
                    birth_date: document.getElementById('settings-birth-date')?.value || '',
                    country: document.getElementById('settings-country')?.value || '',
                    city: document.getElementById('settings-city')?.value || ''
                };
                await window.electronAPI.updateUserProfile(profile);
                this.showSuccessMessage('Profil utilisateur sauvegardé');
            }
        } catch (error) {
            console.error('Error saving user profile:', error);
            this.showErrorMessage('Erreur lors de la sauvegarde du profil');
        }
    }

    async loadApiKeys() {
        try {
            if (window.electronAPI && window.electronAPI.getAllApiKeys) {
                const apiKeys = await window.electronAPI.getAllApiKeys();
                const openaiInput = document.getElementById('settings-api-openai');
                const deepgramInput = document.getElementById('settings-api-deepgram');
                const cartesiaInput = document.getElementById('settings-api-cartesia');

                if (openaiInput && apiKeys.openai) openaiInput.value = apiKeys.openai;
                if (deepgramInput && apiKeys.deepgram) deepgramInput.value = apiKeys.deepgram;
                if (cartesiaInput && apiKeys.cartesia) cartesiaInput.value = apiKeys.cartesia;
            }
        } catch (error) {
            console.error('Error loading API keys:', error);
        }
    }

    async saveApiKeys() {
        try {
            if (window.electronAPI && window.electronAPI.setApiKey) {
                const openaiKey = document.getElementById('settings-api-openai')?.value || '';
                const deepgramKey = document.getElementById('settings-api-deepgram')?.value || '';
                const cartesiaKey = document.getElementById('settings-api-cartesia')?.value || '';

                await window.electronAPI.setApiKey('openai', openaiKey);
                await window.electronAPI.setApiKey('deepgram', deepgramKey);
                await window.electronAPI.setApiKey('cartesia', cartesiaKey);

                await this.saveUserProfile();

                this.showSuccessMessage('Clés API et profil sauvegardés');
            }
        } catch (error) {
            console.error('Error saving API keys:', error);
            this.showErrorMessage('Erreur lors de la sauvegarde des clés API');
        }
    }
}

const settingsManager = new SettingsManager();
window.settingsManager = settingsManager;
