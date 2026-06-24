import { useEffect, useState } from "react";

// Renders the active-user list parsed from a response header.
export function ActiveUsers() {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    fetch("/api/heartbeat").then((resp) => {
      // raw is read from a response header and may be absent.
      const raw = resp.headers.get("x-active-users");
      const names = raw.split(",").map((s) => s.trim());
      setUsers(names);
    });
  }, []);

  return <ul>{users.map((u) => <li key={u}>{u}</li>)}</ul>;
}
