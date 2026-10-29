// ============================================
// UTILITY FUNCTIONS
// ============================================

const Utils = {
    // Format file size
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // Format date
    formatDate(date) {
        if (!date) return 'Just now';
        const d = new Date(date);
        const now = new Date();
        const diff = now - d;
        
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';
        if (diff < 2592000000) return Math.floor(diff / 604800000) + 'w ago';
        if (diff < 31536000000) return Math.floor(diff / 2592000000) + 'mo ago';
        return Math.floor(diff / 31536000000) + 'y ago';
    },

    // Format time
    formatTime(date) {
        if (!date) return '';
        const d = new Date(date);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    // Format date time
    formatDateTime(date) {
        if (!date) return '';
        const d = new Date(date);
        return d.toLocaleString([], {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    // Truncate text
    truncate(text, maxLength = 50) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.slice(0, maxLength) + '...';
    },

    // Escape HTML
    escapeHTML(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // Get initials
    getInitials(name) {
        if (!name) return '';
        return name.split(' ').map(word => word[0]).join('').toUpperCase().slice(0, 2);
    },

    // Generate random ID
    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    },

    // Debounce
    debounce(func, wait = 300) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Throttle
    throttle(func, limit = 300) {
        let inThrottle = false;
        return function(...args) {
            if (!inThrottle) {
                func(...args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    // Show error
    showError(message) {
        const errorEl = document.querySelector('.error-message.show');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.add('show');
            setTimeout(() => {
                errorEl.classList.remove('show');
            }, 5000);
        } else {
            this.showToast(message, 'error');
        }
    },

    // Show toast notification
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }, 100);
    },

    // Copy to clipboard
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            this.showToast('Copied to clipboard!', 'success');
            return true;
        } catch {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                this.showToast('Copied to clipboard!', 'success');
                document.body.removeChild(textarea);
                return true;
            } catch {
                document.body.removeChild(textarea);
                return false;
            }
        }
    },

    // Scroll to element
    scrollToElement(elementId, offset = 0) {
        const element = document.getElementById(elementId);
        if (element) {
            const y = element.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({ top: y, behavior: 'smooth' });
        }
    },

    // Check if element is in viewport
    isInViewport(element) {
        const rect = element.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    },

    // Get query parameters
    getQueryParams() {
        const params = new URLSearchParams(window.location.search);
        const result = {};
        for (const [key, value] of params) {
            result[key] = value;
        }
        return result;
    },

    // Build query string
    buildQueryString(params) {
        return Object.entries(params)
            .filter(([_, value]) => value !== undefined && value !== null)
            .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
            .join('&');
    },

    // Deep clone object
    deepClone(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    // Check if object is empty
    isEmpty(obj) {
        return Object.keys(obj).length === 0;
    },

    // Wait for DOM element
    waitForElement(selector, timeout = 5000) {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();
            const checkInterval = setInterval(() => {
                const element = document.querySelector(selector);
                if (element) {
                    clearInterval(checkInterval);
                    resolve(element);
                } else if (Date.now() - startTime > timeout) {
                    clearInterval(checkInterval);
                    reject(new Error(`Element "${selector}" not found within ${timeout}ms`));
                }
            }, 100);
        });
    }
};

// Make Utils globally available
window.Utils = Utils;

// Add toast styles dynamically
const toastStyles = document.createElement('style');
toastStyles.textContent = `
    .toast {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%) translateY(100px);
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 500;
        z-index: 9999;
        opacity: 0;
        transition: all 0.3s ease;
        max-width: 90%;
        text-align: center;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        min-width: 200px;
    }
    .toast.show {
        opacity: 1;
        transform: translateX(-50%) translateY(0);
    }
    .toast-success { background: #2e7d32; color: white; }
    .toast-error { background: #d32f2f; color: white; }
    .toast-info { background: #1976d2; color: white; }
    .toast-warning { background: #ed6c02; color: white; }
    .toast-dark { background: #1a1a1a; color: white; }
`;
document.head.appendChild(toastStyles);