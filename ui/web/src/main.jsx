import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

// Apply saved theme before first render (prevents flash)
const savedTheme = localStorage.getItem('cc-theme');
const validThemes = ['dark', 'light', 'media-dark', 'media-light'];
if (validThemes.includes(savedTheme)) {
  document.documentElement.setAttribute('data-theme', savedTheme);
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>
);
