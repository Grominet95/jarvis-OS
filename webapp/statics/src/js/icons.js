const Icons = {
    monitor: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="3" width="12" height="8" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <line x1="5" y1="11" x2="11" y2="11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="8" y1="11" x2="8" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    plugins: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <line x1="6" y1="5" x2="10" y2="5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="6" y1="7" x2="10" y2="7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="6" y1="9" x2="8" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    devices: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="5" cy="5" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <circle cx="11" cy="5" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M3 11 C3 9.5 3.5 9 5 9 L11 9 C12.5 9 13 9.5 13 11" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
    </svg>`,
    
    security: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 2 L3 4 L3 8 C3 11.5 5.5 13.5 8 14 C10.5 13.5 13 11.5 13 8 L13 4 Z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linejoin="round"/>
        <path d="M6 8 L7.5 9.5 L10 7" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
    
    location: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="6" r="3" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M8 2 L8 4 M8 8 L8 14 M2 6 L4 6 M12 6 L14 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    feedback: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 2 L8 14 M2 8 L14 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M6 6 L8 8 L10 6" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
    
    settings: `<svg width="16" height="16" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M102.4,222.1H68.5V51.2h33.9V222.1z M68.5,460.8h33.9V358.4H68.5V460.8z M238.7,460.8h33.9V256h-33.9V460.8z M409.6,460.8h33.9v-68.5h-33.9V460.8z M443.5,51.2h-33.9V256h33.9V51.2z M273.3,51.2h-33.9v68.5h33.9V51.2z M136.3,256H33.9C15,256,0,271,0,289.9s15,33.9,33.9,33.9h102.4c18.9,0,33.9-15,33.9-33.9S155.2,256,136.3,256z M307.2,153.6H204.8c-18.9,0-33.9,15-33.9,33.9s15,33.9,33.9,33.9h102.4c18.9,0,33.9-15,33.9-33.9S326.1,153.6,307.2,153.6z M478.1,289.9H375.7c-18.9,0-33.9,15-33.9,33.9s15,33.9,33.9,33.9h102.4c18.9,0,33.9-15,33.9-33.9S497,289.9,478.1,289.9z"/>
    </svg>`,
    
    microphone: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 1.5 C6.6 1.5 5.5 2.6 5.5 4 L5.5 7.5 C5.5 8.9 6.6 10 8 10 C9.4 10 10.5 8.9 10.5 7.5 L10.5 4 C10.5 2.6 9.4 1.5 8 1.5 Z" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M4 7 L4 7.5 C4 9.4 5.4 11 7.2 11.3" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        <path d="M12 7 L12 7.5 C12 9.4 10.6 11 8.8 11.3" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        <line x1="8" y1="12.5" x2="8" y2="14.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="5.5" y1="14.5" x2="10.5" y2="14.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    audio: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 2 L9 16 M3 6 L3 12 M15 6 L15 12 M6 4 L6 14 M12 4 L12 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    general: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="12" height="12" rx="1.5" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M6 7 L12 7 M6 9 L12 9 M6 11 L9 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    advanced: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M9 3 L9 5 M9 13 L9 15 M15 9 L13 9 M5 9 L3 9 M13.5 4.5 L12.2 5.8 M5.8 12.2 L4.5 13.5 M13.5 13.5 L12.2 12.2 M5.8 5.8 L4.5 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    more: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="4" cy="8" r="1.5" fill="currentColor"/>
        <circle cx="8" cy="8" r="1.5" fill="currentColor"/>
        <circle cx="12" cy="8" r="1.5" fill="currentColor"/>
    </svg>`,
    
    wifi: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M2 6 C4 4 6.5 3 8 3 C9.5 3 12 4 14 6" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        <path d="M4 9 C5.5 7.5 6.5 7 8 7 C9.5 7 10.5 7.5 12 9" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        <circle cx="8" cy="12" r="1.5" fill="currentColor"/>
    </svg>`,
    
    battery: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="5" width="10" height="6" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <rect x="12" y="7" width="1.5" height="2" fill="currentColor"/>
        <rect x="3.5" y="6.5" width="7" height="5" fill="currentColor"/>
    </svg>`,
    
    close: `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    
    camera: `<svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="8" y="12" width="32" height="24" rx="2" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/>
        <circle cx="24" cy="24" r="6" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/>
        <circle cx="24" cy="24" r="2" fill="currentColor" opacity="0.3"/>
    </svg>`
};

function setIcon(element, iconName) {
    if (element && Icons[iconName]) {
        element.innerHTML = Icons[iconName];
    }
}
