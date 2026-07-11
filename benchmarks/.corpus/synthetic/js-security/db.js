function fetchUser(db, userId, callback) {
  db.all("SELECT * FROM users WHERE id = ?", [userId], callback);
}

module.exports = { fetchUser };
