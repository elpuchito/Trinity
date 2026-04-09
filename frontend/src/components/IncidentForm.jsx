import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { incidentApi } from '../utils/api';
import {
  IconEdit, IconPaperclip, IconUser, IconUpload, IconRocket,
  IconCheckCircle, IconAlertCircle, IconX, IconImage, IconFile, IconVideo
} from './Icons';

export default function IncidentForm() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
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
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
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
      files.forEach(file => formData.append('attachments', file));

      const result = await incidentApi.create(formData);
      setSubmitted(true);
      setTimeout(() => navigate(`/incident/${result.id}`), 1500);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="animate-pop" style={{ maxWidth: 480, margin: '80px auto', textAlign: 'center' }}>
        <div className="card" style={{ padding: 'var(--space-2xl)' }}>
          <div style={{ marginBottom: 'var(--space-lg)', display: 'flex', justifyContent: 'center' }}>
            <IconCheckCircle size={56} style={{ color: 'var(--stage-completed)' }} />
          </div>
          <h3 style={{ fontWeight: 300, marginBottom: 'var(--space-sm)' }}>Incident Submitted</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', letterSpacing: '0.14px' }}>
            Triage pipeline is starting — redirecting to live view...
          </p>
          <div style={{ marginTop: 'var(--space-lg)' }}>
            <div className="skeleton" style={{ height: 4, borderRadius: 'var(--radius-pill)', width: '60%', margin: '0 auto' }} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-slide-up" style={{ maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 'var(--space-2xl)' }}>
        <h2>Report an Incident</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: 'var(--space-sm)', fontSize: '14px', letterSpacing: '0.14px' }}>
          Submit an incident report and our AI agent will automatically triage, create a ticket, and notify the team.
        </p>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '3px solid var(--severity-p1)', marginBottom: 'var(--space-lg)', padding: 'var(--space-md) var(--space-lg)' }}>
          <p className="flex items-center gap-sm" style={{ color: 'var(--severity-p1)', fontSize: '14px' }}>
            <IconAlertCircle size={14} /> {error}
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card-header">
            <h4 className="flex items-center gap-sm"><IconEdit size={18} /> Incident Details</h4>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="title">Incident Title</label>
            <input id="title" name="title" type="text" className="form-input" placeholder="e.g., Checkout page returns 500 error" value={form.title} onChange={handleChange} required minLength={5} />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="description">
              Description
              <span style={{ float: 'right', fontWeight: 400, textTransform: 'none', letterSpacing: 'normal', color: form.description.length > 0 ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
                {form.description.length} characters
              </span>
            </label>
            <textarea id="description" name="description" className="form-textarea" placeholder="Describe what happened, what you expected, and any error messages you saw..." value={form.description} onChange={handleChange} required minLength={10} rows={6} />
          </div>
        </div>

        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card-header">
            <h4 className="flex items-center gap-sm"><IconPaperclip size={18} /> Attachments</h4>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
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
            <div className="dropzone-icon" style={{ display: 'flex', justifyContent: 'center' }}>
              <IconUpload size={32} style={{ color: 'var(--text-muted)' }} />
            </div>
            <div className="dropzone-text">
              <strong>Click to upload</strong> or drag and drop<br />
              Images, log files, videos (max 10MB each)
            </div>
            <input ref={fileInputRef} type="file" multiple accept="image/*,video/*,.log,.txt,.json,.csv" onChange={(e) => handleFiles(e.target.files)} style={{ display: 'none' }} />
          </div>

          {files.length > 0 && (
            <div style={{ marginTop: 'var(--space-md)', display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
              {files.map((file, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px var(--space-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', fontSize: '14px' }}>
                  <div className="flex items-center gap-md">
                    {file.type.startsWith('image/') ? (
                      <img src={URL.createObjectURL(file)} alt="" style={{ width: 32, height: 32, objectFit: 'cover', borderRadius: 'var(--radius-sm)' }} />
                    ) : file.type.startsWith('video/') ? (
                      <IconVideo size={16} style={{ color: 'var(--text-muted)' }} />
                    ) : (
                      <IconFile size={16} style={{ color: 'var(--text-muted)' }} />
                    )}
                    <span style={{ letterSpacing: '0.14px' }}>{file.name}</span>
                  </div>
                  <div className="flex items-center gap-md">
                    <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      {(file.size / 1024).toFixed(1)} KB
                    </span>
                    <button type="button" onClick={() => removeFile(i)} style={{ background: 'none', border: 'none', color: 'var(--severity-p1)', cursor: 'pointer', display: 'flex' }}>
                      <IconX size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card" style={{ marginBottom: 'var(--space-2xl)' }}>
          <div className="card-header">
            <h4 className="flex items-center gap-sm"><IconUser size={18} /> Reporter Info</h4>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-lg)' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="reporter_name">Your Name</label>
              <input id="reporter_name" name="reporter_name" type="text" className="form-input" placeholder="Jane Smith" value={form.reporter_name} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reporter_email">Your Email</label>
              <input id="reporter_email" name="reporter_email" type="email" className="form-input" placeholder="jane@example.com" value={form.reporter_email} onChange={handleChange} required />
            </div>
          </div>
        </div>

        <button type="submit" className="btn btn-primary btn-lg" disabled={submitting} style={{ width: '100%', justifyContent: 'center' }}>
          {submitting ? (
            <span className="flex items-center gap-sm">Submitting & Triggering Triage...</span>
          ) : (
            <span className="flex items-center gap-sm"><IconRocket size={16} /> Submit Incident Report</span>
          )}
        </button>
      </form>
    </div>
  );
}
