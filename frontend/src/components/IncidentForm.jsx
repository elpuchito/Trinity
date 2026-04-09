import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { incidentApi } from '../utils/api';

export default function IncidentForm() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState([]);
  const [form, setForm] = useState({
    title: '',
    description: '',
    reporter_name: '',
    reporter_email: '',
  });

  function handleChange(e) {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleFiles(newFiles) {
    const fileList = Array.from(newFiles);
    setFiles(prev => [...prev, ...fileList]);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  }

  function removeFile(index) {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('title', form.title);
      formData.append('description', form.description);
      formData.append('reporter_name', form.reporter_name);
      formData.append('reporter_email', form.reporter_email);

      files.forEach(file => {
        formData.append('attachments', file);
      });

      const result = await incidentApi.create(formData);
      navigate(`/incident/${result.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="animate-slide-up" style={{ maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 'var(--space-2xl)' }}>
        <h2>Report an Incident</h2>
        <p className="text-muted" style={{ marginTop: 'var(--space-sm)' }}>
          Submit an incident report and our AI agent will automatically triage, create a ticket, and notify the team.
        </p>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--red)', marginBottom: 'var(--space-lg)', padding: 'var(--space-md)' }}>
          <p style={{ color: 'var(--red)', fontSize: 'var(--text-sm)' }}>⚠️ {error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card-header">
            <h4>📝 Incident Details</h4>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="title">Incident Title</label>
            <input
              id="title"
              name="title"
              type="text"
              className="form-input"
              placeholder="e.g., Checkout page returns 500 error"
              value={form.title}
              onChange={handleChange}
              required
              minLength={5}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="description">Description</label>
            <textarea
              id="description"
              name="description"
              className="form-textarea"
              placeholder="Describe what happened, what you expected, and any error messages you saw..."
              value={form.description}
              onChange={handleChange}
              required
              minLength={10}
              rows={6}
            />
          </div>
        </div>

        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card-header">
            <h4>📎 Attachments</h4>
            <span className="text-muted text-mono" style={{ fontSize: 'var(--text-xs)' }}>
              Screenshots, logs, videos
            </span>
          </div>

          <div
            className={`dropzone ${dragActive ? 'active' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="dropzone-icon">📁</div>
            <div className="dropzone-text">
              <strong>Click to upload</strong> or drag and drop<br />
              Images, log files, videos (max 10MB each)
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,video/*,.log,.txt,.json,.csv"
              onChange={(e) => handleFiles(e.target.files)}
              style={{ display: 'none' }}
            />
          </div>

          {files.length > 0 && (
            <div style={{ marginTop: 'var(--space-md)', display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
              {files.map((file, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: 'var(--space-sm) var(--space-md)',
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-sm)',
                }}>
                  <span>
                    {file.type.startsWith('image/') ? '🖼️' : file.type.startsWith('video/') ? '🎬' : '📄'}
                    {' '}{file.name}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
                    <span className="text-muted text-mono" style={{ fontSize: 'var(--text-xs)' }}>
                      {(file.size / 1024).toFixed(1)} KB
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(i)}
                      style={{ background: 'none', border: 'none', color: 'var(--red)', cursor: 'pointer', fontSize: 'var(--text-md)' }}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card" style={{ marginBottom: 'var(--space-2xl)' }}>
          <div className="card-header">
            <h4>👤 Reporter Info</h4>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-lg)' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="reporter_name">Your Name</label>
              <input
                id="reporter_name"
                name="reporter_name"
                type="text"
                className="form-input"
                placeholder="Jane Smith"
                value={form.reporter_name}
                onChange={handleChange}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reporter_email">Your Email</label>
              <input
                id="reporter_email"
                name="reporter_email"
                type="email"
                className="form-input"
                placeholder="jane@example.com"
                value={form.reporter_email}
                onChange={handleChange}
                required
              />
            </div>
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary btn-lg"
          disabled={submitting}
          style={{ width: '100%', justifyContent: 'center' }}
        >
          {submitting ? (
            <>⏳ Submitting & Triggering Triage...</>
          ) : (
            <>🚀 Submit Incident Report</>
          )}
        </button>
      </form>
    </div>
  );
}
