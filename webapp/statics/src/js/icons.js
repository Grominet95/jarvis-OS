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
    
    settings: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="2.5" stroke="currentColor" stroke-width="1.5" fill="none"/>
        <path d="M8 1 L8 3 M8 13 L8 15 M15 8 L13 8 M3 8 L1 8 M13.5 3.5 L12 5 M4 11 L2.5 12.5 M13.5 12.5 L12 11 M4 5 L2.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
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
