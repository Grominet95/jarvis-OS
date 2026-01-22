const Onboarding = {
    currentStep: -1,
    steps: ['name', 'email', 'birthdate', 'location'],
    userData: {
        name: '',
        email: '',
        birthdate: '',
        country: '',
        city: ''
    },

    async checkFirstInstall() {
        try {
            if (window.electronAPI && window.electronAPI.isFirstInstall) {
                const isFirst = await window.electronAPI.isFirstInstall();
                if (isFirst) {
                    setTimeout(() => {
                        this.show();
                    }, 300);
                } else {
                    this.hide();
                }
            } else {
                const hasCompletedOnboarding = localStorage.getItem('jarvis_onboarding_completed');
                if (!hasCompletedOnboarding) {
                    setTimeout(() => {
                        this.show();
                    }, 300);
                } else {
                    this.hide();
                }
            }
        } catch (error) {
            console.error('Error checking first install:', error);
            this.hide();
        }
    },

    init() {
        const minimizeBtn = document.getElementById('onboarding-minimize-btn');
        const closeBtn = document.getElementById('onboarding-close-btn');
        const onboardingControls = document.querySelector('.onboarding-window-controls');

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
            if (onboardingControls) {
                onboardingControls.style.display = 'none';
            }
        }

        this.checkFirstInstall();
    },

    show() {
        const overlay = document.getElementById('onboarding-overlay');
        if (overlay) {
            overlay.classList.remove('hidden');
            this.showWelcomeAnimation();
        }
    },

    showWelcomeAnimation() {
        const welcomeAnim = document.getElementById('onboarding-welcome-animation');
        const welcomeMessage = welcomeAnim ? welcomeAnim.querySelector('.welcome-message') : null;
        const progress = document.querySelector('.onboarding-progress');
        const skipBtn = document.getElementById('onboarding-skip-all');

        if (welcomeAnim) {
            welcomeAnim.classList.remove('hidden');
            if (progress) {
                progress.style.visibility = 'hidden';
                progress.style.opacity = '0';
            }
            if (skipBtn) {
                skipBtn.style.visibility = 'hidden';
                skipBtn.style.opacity = '0';
                skipBtn.style.pointerEvents = 'none';
            }

            setTimeout(() => {
                if (welcomeMessage) {
                    welcomeMessage.style.opacity = '0';
                    welcomeMessage.style.transition = 'opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                }
            }, 2500);

            setTimeout(() => {
                if (welcomeAnim) {
                    welcomeAnim.classList.add('hidden');
                }
            }, 3500);

            setTimeout(() => {
                this.showStep(0);

                setTimeout(() => {
                    if (progress) {
                        progress.style.visibility = 'visible';
                        setTimeout(() => {
                            progress.style.opacity = '1';
                        }, 50);
                    }
                    if (skipBtn) {
                        skipBtn.style.visibility = 'visible';
                        skipBtn.style.pointerEvents = 'auto';
                        setTimeout(() => {
                            skipBtn.classList.add('visible');
                            skipBtn.style.opacity = '';
                        }, 50);
                    }
                }, 400);
            }, 4500);
        } else {
            this.showStep(0);
        }
    },

    hide() {
        const overlay = document.getElementById('onboarding-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
            setTimeout(() => {
                overlay.style.display = 'none';
            }, 400);
        }
    },

    showStep(stepIndex) {
        const steps = document.querySelectorAll('.onboarding-step');
        const currentActiveStep = Array.from(steps).find(step => step.classList.contains('active'));

        if (currentActiveStep && currentActiveStep !== steps[stepIndex]) {
            currentActiveStep.classList.add('exiting');
            setTimeout(() => {
                currentActiveStep.classList.remove('active', 'exiting');
                currentActiveStep.style.display = 'none';

                this.currentStep = stepIndex;
                const nextStep = steps[stepIndex];
                if (nextStep) {
                    nextStep.style.display = 'flex';
                    requestAnimationFrame(() => {
                        nextStep.classList.add('active');
                    });
                }

                const skipBtn = document.getElementById('onboarding-skip-all');
                const welcomeAnim = document.getElementById('onboarding-welcome-animation');

                if (skipBtn && (!welcomeAnim || welcomeAnim.classList.contains('hidden'))) {
                    setTimeout(() => {
                        skipBtn.style.visibility = 'visible';
                        skipBtn.style.pointerEvents = 'auto';
                        setTimeout(() => {
                            skipBtn.classList.add('visible');
                            skipBtn.style.opacity = '';
                        }, 100);
                    }, 300);
                }

                this.updateProgress();
                this.setupStepHandlers();
            }, 300);
        } else {
            this.currentStep = stepIndex;
            steps.forEach((step, index) => {
                if (index === stepIndex) {
                    step.style.display = 'flex';
                    requestAnimationFrame(() => {
                        step.classList.add('active');
                    });
                } else {
                    step.classList.remove('active');
                    step.style.display = 'none';
                }
            });

            const skipBtn = document.getElementById('onboarding-skip-all');
            const welcomeAnim = document.getElementById('onboarding-welcome-animation');

            if (skipBtn && (!welcomeAnim || welcomeAnim.classList.contains('hidden'))) {
                setTimeout(() => {
                    skipBtn.style.visibility = 'visible';
                    skipBtn.style.pointerEvents = 'auto';
                    setTimeout(() => {
                        skipBtn.classList.add('visible');
                        skipBtn.style.opacity = '';
                    }, 100);
                }, 300);
            }

            this.updateProgress();
            this.setupStepHandlers();
        }
    },

    updateProgress() {
        const dots = document.querySelectorAll('.onboarding-progress-dot');
        dots.forEach((dot, index) => {
            if (index === this.currentStep) {
                dot.classList.add('active');
            } else {
                dot.classList.remove('active');
            }
        });
    },

    setupStepHandlers() {
        const skipAllBtn = document.getElementById('onboarding-skip-all');
        if (skipAllBtn) {
            skipAllBtn.onclick = () => this.completeOnboarding();
        }

        if (this.currentStep === 0) {
            const nameInput = document.getElementById('onboarding-name-input');
            const continueBtn = document.getElementById('onboarding-name-continue');

            if (nameInput && continueBtn) {
                nameInput.onkeypress = (e) => {
                    if (e.key === 'Enter') {
                        this.handleNameSubmit();
                    }
                };

                continueBtn.onclick = () => this.handleNameSubmit();
            }
        } else if (this.currentStep === 1) {
            const emailInput = document.getElementById('onboarding-email-input');
            const continueBtn = document.getElementById('onboarding-email-continue');

            if (emailInput && continueBtn) {
                emailInput.onkeypress = (e) => {
                    if (e.key === 'Enter') {
                        this.handleEmailSubmit();
                    }
                };

                continueBtn.onclick = () => this.handleEmailSubmit();
            }
        } else if (this.currentStep === 2) {
            const birthdateInput = document.getElementById('onboarding-birthdate-input');
            const continueBtn = document.getElementById('onboarding-birthdate-continue');

            if (birthdateInput && continueBtn) {
                continueBtn.onclick = () => this.handleBirthdateSubmit();
            }
        } else if (this.currentStep === 3) {
            const countryInput = document.getElementById('onboarding-country-input');
            const cityInput = document.getElementById('onboarding-city-input');
            const continueBtn = document.getElementById('onboarding-location-continue');

            if (countryInput && cityInput && continueBtn) {
                const handleLocationSubmit = () => this.handleLocationSubmit();
                countryInput.onkeypress = (e) => {
                    if (e.key === 'Enter') {
                        handleLocationSubmit();
                    }
                };
                cityInput.onkeypress = (e) => {
                    if (e.key === 'Enter') {
                        handleLocationSubmit();
                    }
                };

                continueBtn.onclick = handleLocationSubmit;
            }
        }
    },

    nextStep() {
        if (this.currentStep < this.steps.length - 1) {
            this.showStep(this.currentStep + 1);
        }
    },

    handleNameSubmit() {
        const nameInput = document.getElementById('onboarding-name-input');
        const name = nameInput ? nameInput.value.trim() : '';
        if (name) {
            this.userData.name = name;
            const emailNameSpan = document.getElementById('step-email-name');
            if (emailNameSpan) {
                emailNameSpan.textContent = name;
            }
        }
        this.nextStep();
    },

    handleEmailSubmit() {
        const emailInput = document.getElementById('onboarding-email-input');
        const email = emailInput ? emailInput.value.trim() : '';
        if (email && email.includes('@')) {
            this.userData.email = email;
            this.nextStep();
        }
    },

    handleBirthdateSubmit() {
        const birthdateInput = document.getElementById('onboarding-birthdate-input');
        const birthdate = birthdateInput ? birthdateInput.value : '';
        if (birthdate) {
            this.userData.birthdate = birthdate;
            this.nextStep();
        }
    },

    handleLocationSubmit() {
        const countryInput = document.getElementById('onboarding-country-input');
        const cityInput = document.getElementById('onboarding-city-input');
        const country = countryInput ? countryInput.value.trim() : '';
        const city = cityInput ? cityInput.value.trim() : '';
        if (country && city) {
            this.userData.country = country;
            this.userData.city = city;
            this.showConfiguring();
        }
    },

    showConfiguring() {
        const progress = document.querySelector('.onboarding-progress');
        const skipBtn = document.getElementById('onboarding-skip-all');

        if (progress) {
            progress.style.visibility = 'hidden';
            progress.style.opacity = '0';
        }
        if (skipBtn) {
            skipBtn.style.visibility = 'hidden';
            skipBtn.style.opacity = '0';
            skipBtn.style.pointerEvents = 'none';
        }

        const steps = document.querySelectorAll('.onboarding-step');
        const currentActiveStep = Array.from(steps).find(step => step.classList.contains('active'));

        if (currentActiveStep) {
            currentActiveStep.classList.add('exiting');
            setTimeout(() => {
                currentActiveStep.classList.remove('active', 'exiting');
                currentActiveStep.style.display = 'none';

                const configuringStep = document.getElementById('step-configuring');
                if (configuringStep) {
                    configuringStep.style.display = 'flex';
                    requestAnimationFrame(() => {
                        configuringStep.classList.add('active');
                    });
                }

                setTimeout(() => {
                    this.completeOnboarding();
                }, 3500);
            }, 300);
        }
    },

    handleLogin() {
        console.log('Login clicked');
        const name = this.userData.name || 'Utilisateur';
        alert(`Connexion en cours...\nBonjour ${name} !`);
        this.completeOnboarding();
    },

    handleSignup() {
        console.log('Signup clicked');
        window.open('https://jarvis.example.com/signup', '_blank');
        const name = this.userData.name || 'Utilisateur';
        setTimeout(() => {
            alert(`Inscription ouverte dans le navigateur.\nBienvenue ${name} !`);
            this.completeOnboarding();
        }, 500);
    },

    async completeOnboarding() {
        try {
            if (window.electronAPI && window.electronAPI.updateUserProfile) {
                const profile = {
                    first_name: this.userData.name || '',
                    birth_date: this.userData.birthdate || '',
                    country: this.userData.country || '',
                    city: this.userData.city || ''
                };
                await window.electronAPI.updateUserProfile(profile);
            } else {
                localStorage.setItem('jarvis_onboarding_completed', 'true');
                if (this.userData.name) {
                    localStorage.setItem('jarvis_user_name', this.userData.name);
                }
                if (this.userData.email) {
                    localStorage.setItem('jarvis_user_email', this.userData.email);
                }
                if (this.userData.birthdate) {
                    localStorage.setItem('jarvis_user_birthdate', this.userData.birthdate);
                }
                if (this.userData.country) {
                    localStorage.setItem('jarvis_user_country', this.userData.country);
                }
                if (this.userData.city) {
                    localStorage.setItem('jarvis_user_city', this.userData.city);
                }
            }
        } catch (error) {
            console.error('Error completing onboarding:', error);
        }

        const overlay = document.getElementById('onboarding-overlay');
        const appContainer = document.querySelector('.app-container');

        if (overlay) {
            overlay.classList.add('fading-out');
            setTimeout(() => {
                overlay.classList.add('hidden');
                setTimeout(() => {
                    overlay.style.display = 'none';
                    if (appContainer) {
                        appContainer.classList.add('visible');
                    }
                    this.showWelcomeMessage();
                }, 400);
            }, 600);
        } else {
            if (appContainer) {
                appContainer.classList.add('visible');
            }
            this.showWelcomeMessage();
        }
    },

    showWelcomeMessage() {
        const chatContainer = document.getElementById('chat-container');
        const userGreeting = document.getElementById('user-greeting');
        const userName = this.userData.name || localStorage.getItem('jarvis_user_name') || 'Utilisateur';

        if (userGreeting && userName) {
            userGreeting.textContent = `Bonjour ${userName}`;
            setTimeout(() => {
                userGreeting.classList.add('visible');
            }, 300);
        }

        if (chatContainer) {
            setTimeout(() => {
                const welcomeMessage = document.createElement('div');
                welcomeMessage.className = 'message system-message';
                welcomeMessage.innerHTML = `<p>Bonjour ${userName} ! Comment puis-je t'aider aujourd'hui ?</p>`;
                chatContainer.appendChild(welcomeMessage);

                setTimeout(() => {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }, 100);
            }, 500);
        }
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Onboarding.init());
} else {
    Onboarding.init();
}
