const API_BASE_URL = 'http://localhost:8000/api';

// Helper function for making API calls
async function apiCall(endpoint, method = 'GET', data = null) {
    const headers = {
        'Content-Type': 'application/json',
    };
    
    const token = localStorage.getItem('access_token');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        method: method,
        headers: headers,
    };

    if (data) {
        config.body = JSON.stringify(data);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    return await response.json();
}

// Register function
async function register(event) {
    event.preventDefault();
    const username = document.getElementById('reg-username').value;
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    const bio = document.getElementById('reg-bio').value;

    try {
        const data = await apiCall('/users/register/', 'POST', { username, email, password, bio });
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);
        showUserProfile();
    } catch (error) {
        console.error('Registration failed:', error);
    }
}

// Login function
async function login(event) {
    event.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
        const data = await apiCall('/users/login/', 'POST', { username, password });
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);
        showUserProfile();
    } catch (error) {
        console.error('Login failed:', error);
    }
}

// Logout function
async function logout() {
    try {
        await apiCall('/users/logout/', 'POST', { refresh: localStorage.getItem('refresh_token') });
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        showAuthForms();
    } catch (error) {
        console.error('Logout failed:', error);
    }
}

// Show user profile
async function showUserProfile() {
    try {
        const userData = await apiCall('/users/profile/');
        document.getElementById('auth-container').style.display = 'none';
        document.getElementById('user-profile').style.display = 'block';
        document.getElementById('profile-info').textContent = `Welcome, ${userData.username}! Email: ${userData.email}, Bio: ${userData.bio}`;
    } catch (error) {
        console.error('Failed to fetch user profile:', error);
        showAuthForms();
    }
}

// Show auth forms
function showAuthForms() {
    document.getElementById('auth-container').style.display = 'flex';
    document.getElementById('user-profile').style.display = 'none';
}

// Event listeners
document.getElementById('register').addEventListener('submit', register);
document.getElementById('login').addEventListener('submit', login);
document.getElementById('logout').addEventListener('click', logout);

// Check if user is already logged in
if (localStorage.getItem('access_token')) {
    showUserProfile();
} else {
    showAuthForms();
}