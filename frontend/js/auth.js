// ============================================
// AUTHENTICATION HELPERS
// ============================================

const Auth = {
    // Check if user is authenticated
    isAuthenticated() {
        return !!localStorage.getItem('access_token');
    },

    // Get current user
    getCurrentUser() {
        try {
            const user = localStorage.getItem('user');
            return user ? JSON.parse(user) : null;
        } catch {
            return null;
        }
    },

    // Save user
    saveUser(user) {
        localStorage.setItem('user', JSON.stringify(user));
    },

    // Clear auth data
    clear() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    },

    // Get cookie by name
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    },

    // Decode JWT token
    decodeToken(token) {
        try {
            const payload = token.split('.')[1];
            return JSON.parse(atob(payload));
        } catch {
            return null;
        }
    },

    // Check if token is expired
    isTokenExpired(token) {
        const decoded = this.decodeToken(token);
        if (!decoded) return true;
        return decoded.exp * 1000 < Date.now();
    },

    // Auto-refresh token if needed
    async refreshIfNeeded() {
        const token = localStorage.getItem('access_token');
        if (!token) return false;
        if (!this.isTokenExpired(token)) return true;

        try {
            const refreshToken = localStorage.getItem('refresh_token') || this.getCookie('refresh_token');
            if (!refreshToken) return false;
            const result = await AuthAPI.refresh({ refresh_token: refreshToken });
            if (result.access_token) {
                API.setToken(result.access_token);
                return true;
            }
            return false;
        } catch {
            return false;
        }
    },

    // Get auth headers for API requests
    getAuthHeaders() {
        const token = localStorage.getItem('access_token');
        return {
            'Authorization': token ? `Bearer ${token}` : '',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
    },

    // Validate password strength
    validatePassword(password) {
        const errors = [];
        if (password.length < 8) {
            errors.push('Password must be at least 8 characters long');
        }
        if (!/[a-z]/.test(password)) {
            errors.push('Password must contain at least one lowercase letter');
        }
        if (!/[A-Z]/.test(password)) {
            errors.push('Password must contain at least one uppercase letter');
        }
        if (!/\d/.test(password)) {
            errors.push('Password must contain at least one number');
        }
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
            errors.push('Password must contain at least one special character');
        }
        return {
            valid: errors.length === 0,
            errors: errors
        };
    },

    // Get password strength (0-5)
    getPasswordStrength(password) {
        let strength = 0;
        if (password.length >= 8) strength++;
        if (/[a-z]/.test(password)) strength++;
        if (/[A-Z]/.test(password)) strength++;
        if (/\d/.test(password)) strength++;
        if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength++;
        return strength;
    },

    // Get password strength label
    getStrengthLabel(strength) {
        const labels = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong', 'Very Strong'];
        return labels[Math.min(strength, labels.length - 1)];
    },

    // Get password strength color
    getStrengthColor(strength) {
        const colors = ['#f44336', '#f44336', '#ff9800', '#ffeb3b', '#4caf50', '#2e7d32'];
        return colors[Math.min(strength, colors.length - 1)];
    },

    // Validate email
    validateEmail(email) {
        const re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        return re.test(email);
    },

    // Validate username
    validateUsername(username) {
        if (!username || username.length < 3) {
            return { valid: false, error: 'Username must be at least 3 characters' };
        }
        if (username.length > 50) {
            return { valid: false, error: 'Username must be less than 50 characters' };
        }
        if (!/^[a-zA-Z0-9_]+$/.test(username)) {
            return { valid: false, error: 'Username can only contain letters, numbers, and underscores' };
        }
        return { valid: true };
    },

    // Show auth error
    showError(message) {
        const errorEl = document.querySelector('.error-message.show');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.add('show');
            setTimeout(() => {
                errorEl.classList.remove('show');
            }, 5000);
        } else {
            Utils.showToast(message, 'error');
        }
    },

    // Clear auth errors
    clearErrors() {
        document.querySelectorAll('.error-message').forEach(el => {
            el.classList.remove('show');
            el.textContent = '';
        });
        document.querySelectorAll('.form-group input.error').forEach(el => {
            el.classList.remove('error');
        });
    },

    // Mark form fields with errors
    markErrorFields(fieldErrors) {
        Object.keys(fieldErrors).forEach(field => {
            const input = document.querySelector(`[name="${field}"]`);
            if (input) {
                input.classList.add('error');
                const errorEl = document.getElementById(`${field}-error`);
                if (errorEl) {
                    errorEl.textContent = fieldErrors[field];
                    errorEl.classList.add('show');
                }
            }
        });
    },

    // ✅ FIXED: Handle login form submission with app check
    handleLogin(e) {
        e.preventDefault();
        this.clearErrors();

        const identifier = document.getElementById('login-identifier').value.trim();
        const password = document.getElementById('login-password').value;

        if (!identifier) {
            this.showError('Please enter username or email');
            document.getElementById('login-identifier').focus();
            return;
        }

        if (!password) {
            this.showError('Please enter your password');
            document.getElementById('login-password').focus();
            return;
        }

        // Wait for app to be initialized
        const checkApp = () => {
            if (window.app && typeof window.app.login === 'function') {
                window.app.login(identifier, password);
            } else {
                // App not ready, try again in 100ms
                setTimeout(checkApp, 100);
            }
        };
        checkApp();
    },

    // ✅ FIXED: Handle register form submission with app check
    handleRegister(e) {
        e.preventDefault();
        this.clearErrors();

        const username = document.getElementById('register-username').value.trim();
        const email = document.getElementById('register-email').value.trim();
        const fullName = document.getElementById('register-fullname').value.trim();
        const password = document.getElementById('register-password').value;
        const confirm = document.getElementById('register-confirm').value;

        // Validate username
        const usernameValidation = this.validateUsername(username);
        if (!usernameValidation.valid) {
            this.showError(usernameValidation.error);
            document.getElementById('register-username').focus();
            return;
        }

        // Validate email
        if (!this.validateEmail(email)) {
            this.showError('Please enter a valid email address');
            document.getElementById('register-email').focus();
            return;
        }

        // Validate password
        const passwordValidation = this.validatePassword(password);
        if (!passwordValidation.valid) {
            this.showError(passwordValidation.errors.join('\n'));
            document.getElementById('register-password').focus();
            return;
        }

        // Check password match
        if (password !== confirm) {
            this.showError('Passwords do not match');
            document.getElementById('register-confirm').focus();
            return;
        }

        // Wait for app to be initialized
        const checkApp = () => {
            if (window.app && typeof window.app.register === 'function') {
                window.app.register(username, email, password, fullName);
            } else {
                setTimeout(checkApp, 100);
            }
        };
        checkApp();
    },

    // Handle logout
    handleLogout() {
        if (window.confirm('Are you sure you want to logout?')) {
            if (window.app && typeof window.app.logout === 'function') {
                window.app.logout();
            } else {
                // Fallback logout
                localStorage.clear();
                window.location.reload();
            }
        }
    },

    // Handle forgot password
    handleForgotPassword(e) {
        e.preventDefault();
        const email = document.getElementById('forgot-email').value.trim();
        if (!this.validateEmail(email)) {
            this.showError('Please enter a valid email address');
            return;
        }
        AuthAPI.forgotPassword({ email })
            .then(() => {
                Utils.showToast('Password reset link sent to your email', 'success');
            })
            .catch(error => {
                this.showError(error.message || 'Failed to send reset link');
            });
    },

    // Setup auth event listeners
    setupAuthEvents() {
        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', this.handleLogin.bind(this));
        }

        // Register form
        const registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.addEventListener('submit', this.handleRegister.bind(this));
        }

        // Logout button
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', this.handleLogout.bind(this));
        }

        // Show register
        const showRegister = document.getElementById('show-register');
        if (showRegister) {
            showRegister.addEventListener('click', (e) => {
                e.preventDefault();
                this.clearErrors();
                document.querySelectorAll('.auth-form-page').forEach(p => p.classList.remove('active'));
                document.getElementById('register-page').classList.add('active');
            });
        }

        // Show login
        const showLogin = document.getElementById('show-login');
        if (showLogin) {
            showLogin.addEventListener('click', (e) => {
                e.preventDefault();
                this.clearErrors();
                document.querySelectorAll('.auth-form-page').forEach(p => p.classList.remove('active'));
                document.getElementById('login-page').classList.add('active');
            });
        }

        // Forgot password
        const forgotLink = document.getElementById('forgot-password-link');
        if (forgotLink) {
            forgotLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.clearErrors();
                this.showForgotPasswordModal();
            });
        }

        // Password strength checker
        const passwordInput = document.getElementById('register-password');
        if (passwordInput) {
            passwordInput.addEventListener('input', (e) => {
                this.updatePasswordStrengthUI(e.target.value);
            });
        }

        // Enter key handlers
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const activePage = document.querySelector('.auth-form-page.active');
                if (activePage) {
                    const form = activePage.querySelector('form');
                    if (form) {
                        form.dispatchEvent(new Event('submit'));
                    }
                }
            }
        });
    },

    // Show forgot password modal
    showForgotPasswordModal() {
        if (window.app && typeof window.app.openModal === 'function') {
            window.app.openModal('Forgot Password', `
                <p>Enter your email address and we'll send you a password reset link.</p>
                <form id="forgot-password-form" style="margin-top:16px;">
                    <div class="form-group">
                        <label for="forgot-email">Email Address</label>
                        <input type="email" id="forgot-email" placeholder="Enter your email" required />
                    </div>
                    <div style="display:flex;gap:8px;margin-top:16px;">
                        <button type="submit" class="btn-primary">Send Reset Link</button>
                        <button type="button" class="btn-secondary" onclick="closeModal()">Cancel</button>
                    </div>
                </form>
                <div id="forgot-error" class="error-message"></div>
                <script>
                    document.getElementById('forgot-password-form').addEventListener('submit', (e) => {
                        e.preventDefault();
                        const email = document.getElementById('forgot-email').value.trim();
                        if (!email) {
                            document.getElementById('forgot-error').textContent = 'Please enter your email';
                            document.getElementById('forgot-error').classList.add('show');
                            return;
                        }
                        Auth.handleForgotPassword(e);
                    });
                <\/script>
            `);
        }
    },

    // Update password strength UI
    updatePasswordStrengthUI(password) {
        const container = document.getElementById('password-strength');
        if (!container) return;

        const strength = this.getPasswordStrength(password);
        const label = this.getStrengthLabel(strength);
        const color = this.getStrengthColor(strength);
        const width = (strength / 5) * 100;

        container.innerHTML = `
            <div style="margin-top:4px;">
                <div style="height:4px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:${width}%;background:${color};border-radius:4px;transition:width 0.3s;"></div>
                </div>
                <span style="font-size:12px;color:${color};">${label}</span>
            </div>
        `;
    },

    // Auto-login if token exists
    async autoLogin() {
        if (this.isAuthenticated()) {
            const token = localStorage.getItem('access_token');
            if (!this.isTokenExpired(token)) {
                try {
                    const result = await AuthAPI.getProfile();
                    if (result.user) {
                        Auth.saveUser(result.user);
                        if (window.app) {
                            window.app.currentUser = result.user;
                            window.app.showMainApp();
                            window.app.loadUserData();
                        }
                        return true;
                    }
                } catch (error) {
                    console.error('Auto-login failed:', error);
                    this.clear();
                }
            } else {
                // Try to refresh token
                const refreshed = await this.refreshIfNeeded();
                if (refreshed) {
                    return this.autoLogin();
                }
                this.clear();
            }
        }
        return false;
    }
};

// Make Auth globally available
window.Auth = Auth;

// Auto-initialize auth events when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait a bit for app to initialize
    setTimeout(() => {
        Auth.setupAuthEvents();
        console.log('🔐 Auth system initialized');
    }, 200);
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Auth;
}