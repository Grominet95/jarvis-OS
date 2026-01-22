const Database = require('better-sqlite3');
const path = require('path');
const { app } = require('electron');
const fs = require('fs');

let db = null;
let dbPath = null;

function getDbPath() {
  if (!dbPath) {
    try {
      const userDataPath = app.getPath('userData');
      if (!fs.existsSync(userDataPath)) {
        fs.mkdirSync(userDataPath, { recursive: true });
        console.log('[DATABASE] Created userData directory:', userDataPath);
      }
      dbPath = path.join(userDataPath, 'jarvis.db');
      console.log('[DATABASE] Database path:', dbPath);
    } catch (error) {
      console.error('[DATABASE] Error getting userData path:', error);
      const fallbackPath = path.join(__dirname, '..', 'jarvis.db');
      dbPath = fallbackPath;
      console.log('[DATABASE] Using fallback path:', dbPath);
    }
  }
  return dbPath;
}

function getDatabase() {
  if (!db) {
    const path = getDbPath();
    const dbExists = fs.existsSync(path);
    console.log('[DATABASE] Database exists:', dbExists, 'at:', path);
    
    try {
      db = new Database(path);
      console.log('[DATABASE] Database connection opened');
      
      if (!dbExists) {
        console.log('[DATABASE] Initializing new database...');
        initializeDatabase();
      } else {
        console.log('[DATABASE] Using existing database');
      }
    } catch (error) {
      console.error('[DATABASE] Error opening database:', error);
      throw error;
    }
  }
  return db;
}

function initializeDatabase() {
  const db = getDatabase();
  
  db.exec(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS user_profile (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      first_name TEXT,
      birth_date TEXT,
      country TEXT,
      city TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS api_keys (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      service TEXT NOT NULL UNIQUE,
      api_key TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);
    CREATE INDEX IF NOT EXISTS idx_api_keys_service ON api_keys(service);
  `);
  
  const stmt = db.prepare('INSERT OR IGNORE INTO user_profile (id) VALUES (1)');
  stmt.run();
  
  console.log('[DATABASE] Database initialized at:', dbPath);
}

function getSetting(key) {
  const db = getDatabase();
  const stmt = db.prepare('SELECT value FROM settings WHERE key = ?');
  const result = stmt.get(key);
  return result ? result.value : null;
}

function setSetting(key, value) {
  const db = getDatabase();
  const stmt = db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)');
  stmt.run(key, value);
  return { success: true };
}

function getUserProfile() {
  const db = getDatabase();
  const stmt = db.prepare('SELECT * FROM user_profile WHERE id = 1');
  return stmt.get() || {};
}

function updateUserProfile(profile) {
  const db = getDatabase();
  const stmt = db.prepare(`
    UPDATE user_profile 
    SET first_name = ?, birth_date = ?, country = ?, city = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = 1
  `);
  stmt.run(profile.first_name || null, profile.birth_date || null, profile.country || null, profile.city || null);
  return { success: true };
}

function getApiKey(service) {
  const db = getDatabase();
  const stmt = db.prepare('SELECT api_key FROM api_keys WHERE service = ?');
  const result = stmt.get(service);
  return result ? result.api_key : null;
}

function setApiKey(service, apiKey) {
  const db = getDatabase();
  const stmt = db.prepare('INSERT OR REPLACE INTO api_keys (service, api_key, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)');
  stmt.run(service, apiKey || null);
  return { success: true };
}

function getAllApiKeys() {
  const db = getDatabase();
  const stmt = db.prepare('SELECT service, api_key FROM api_keys');
  return stmt.all().reduce((acc, row) => {
    acc[row.service] = row.api_key;
    return acc;
  }, {});
}

function isFirstInstall() {
  const db = getDatabase();
  const stmt = db.prepare('SELECT COUNT(*) as count FROM api_keys WHERE api_key IS NOT NULL AND api_key != ?');
  const result = stmt.get('');
  return result.count === 0;
}

module.exports = {
  getDatabase,
  getSetting,
  setSetting,
  getUserProfile,
  updateUserProfile,
  getApiKey,
  setApiKey,
  getAllApiKeys,
  isFirstInstall,
  dbPath
};
