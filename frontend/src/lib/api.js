import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const SESSION_KEY = "unlockvault_session";

export function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random()}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export const client = axios.create({ baseURL: API });

export const api = {
  listFiles: (sid) => client.get(`/files/${sid}`).then((r) => r.data.files),
  upload: (sid, files, onProgress) => {
    const fd = new FormData();
    fd.append("session_id", sid);
    files.forEach((f) => fd.append("files", f));
    return client
      .post("/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: onProgress,
      })
      .then((r) => r.data.files);
  },
  match: (sid, passwords) =>
    client.post("/match-passwords", { session_id: sid, passwords }).then((r) => r.data),
  unlock: (sid, file_ids) =>
    client.post("/unlock", { session_id: sid, file_ids }).then((r) => r.data),
  remove: (sid, id) => client.delete(`/file/${sid}/${id}`).then((r) => r.data),
  removeMany: (sid, file_ids) =>
    client.post("/delete-bulk", { session_id: sid, file_ids }).then((r) => r.data),
  replace: (sid, id, file) => {
    const fd = new FormData();
    fd.append("session_id", sid);
    fd.append("file_id", id);
    fd.append("file", file);
    return client
      .post("/replace", fd, { headers: { "Content-Type": "multipart/form-data" } })
      .then((r) => r.data.file);
  },
  merge: (sid, file_ids, output_name) =>
    client.post("/merge-pdf", { session_id: sid, file_ids, output_name }).then((r) => r.data.file),
  downloadFileUrl: (sid, id) => `${API}/download/${sid}/${id}`,
  downloadZipUrl: (sid) => `${API}/download-zip/${sid}?only=unlocked`,
};
