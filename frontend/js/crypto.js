// ============================================
// CRYPTOGRAPHY UTILITIES
// ============================================

class CryptoUtils {
    // Generate RSA key pair
    static async generateRSAKeyPair() {
        return await window.crypto.subtle.generateKey(
            {
                name: 'RSA-OAEP',
                modulusLength: 2048,
                publicExponent: new Uint8Array([1, 0, 1]),
                hash: 'SHA-256',
            },
            true,
            ['encrypt', 'decrypt']
        );
    }

    // Export public key
    static async exportPublicKey(key) {
        const exported = await window.crypto.subtle.exportKey('spki', key);
        return btoa(String.fromCharCode(...new Uint8Array(exported)));
    }

    // Import public key
    static async importPublicKey(keyData) {
        const binaryString = atob(keyData);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return await window.crypto.subtle.importKey(
            'spki',
            bytes,
            {
                name: 'RSA-OAEP',
                hash: 'SHA-256',
            },
            true,
            ['encrypt']
        );
    }

    // Import private key
    static async importPrivateKey(keyData) {
        const binaryString = atob(keyData);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return await window.crypto.subtle.importKey(
            'pkcs8',
            bytes,
            {
                name: 'RSA-OAEP',
                hash: 'SHA-256',
            },
            true,
            ['decrypt']
        );
    }

    // Encrypt with public key
    static async encryptWithPublicKey(publicKey, data) {
        const encoded = new TextEncoder().encode(data);
        return await window.crypto.subtle.encrypt(
            {
                name: 'RSA-OAEP',
            },
            publicKey,
            encoded
        );
    }

    // Decrypt with private key
    static async decryptWithPrivateKey(privateKey, encrypted) {
        const decrypted = await window.crypto.subtle.decrypt(
            {
                name: 'RSA-OAEP',
            },
            privateKey,
            encrypted
        );
        return new TextDecoder().decode(decrypted);
    }

    // Generate AES key
    static async generateAESKey() {
        return await window.crypto.subtle.generateKey(
            {
                name: 'AES-GCM',
                length: 256,
            },
            true,
            ['encrypt', 'decrypt']
        );
    }

    // Encrypt with AES-GCM
    static async encryptAES(key, data) {
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const encoded = new TextEncoder().encode(data);
        const encrypted = await window.crypto.subtle.encrypt(
            {
                name: 'AES-GCM',
                iv: iv,
            },
            key,
            encoded
        );
        return {
            iv: btoa(String.fromCharCode(...iv)),
            data: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
        };
    }

    // Decrypt with AES-GCM
    static async decryptAES(key, iv, data) {
        const ivBytes = Uint8Array.from(atob(iv), c => c.charCodeAt(0));
        const dataBytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
        const decrypted = await window.crypto.subtle.decrypt(
            {
                name: 'AES-GCM',
                iv: ivBytes,
            },
            key,
            dataBytes
        );
        return new TextDecoder().decode(decrypted);
    }

    // Generate random token
    static generateToken(length = 32) {
        const array = new Uint8Array(length);
        window.crypto.getRandomValues(array);
        return btoa(String.fromCharCode(...array));
    }

    // Hash password (for client-side verification)
    static async hashPassword(password) {
        const encoded = new TextEncoder().encode(password);
        const hash = await window.crypto.subtle.digest('SHA-256', encoded);
        return btoa(String.fromCharCode(...new Uint8Array(hash)));
    }

    // Generate random string
    static generateRandomString(length = 32) {
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        let result = '';
        const array = new Uint8Array(length);
        window.crypto.getRandomValues(array);
        for (let i = 0; i < length; i++) {
            result += chars[array[i] % chars.length];
        }
        return result;
    }

    // Encrypt message with password (simple client-side encryption)
    static async encryptMessageWithPassword(message, password) {
        const key = await this.deriveKey(password);
        return await this.encryptAES(key, message);
    }

    // Decrypt message with password
    static async decryptMessageWithPassword(encrypted, password) {
        const key = await this.deriveKey(password);
        return await this.decryptAES(key, encrypted.iv, encrypted.data);
    }

    // Derive key from password
    static async deriveKey(password) {
        const encoder = new TextEncoder();
        const keyMaterial = await window.crypto.subtle.importKey(
            'raw',
            encoder.encode(password),
            'PBKDF2',
            false,
            ['deriveKey']
        );
        return await window.crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: encoder.encode('salt'),
                iterations: 100000,
                hash: 'SHA-256',
            },
            keyMaterial,
            {
                name: 'AES-GCM',
                length: 256,
            },
            true,
            ['encrypt', 'decrypt']
        );
    }
}

// Make CryptoUtils globally available
window.CryptoUtils = CryptoUtils;