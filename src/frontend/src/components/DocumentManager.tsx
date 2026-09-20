import React, { useState } from 'react';
import { FileText, Upload, CheckCircle2, AlertCircle, Trash2, Database } from 'lucide-react';

interface ManagedDocument {
  id: string;
  name: string;
  sizeBytes: number;
  type: string;
  uploadedAt: string;
  chunksCount: number;
  status: 'indexed' | 'processing' | 'error';
}

export const DocumentManager: React.FC = () => {
  const [documents, setDocuments] = useState<ManagedDocument[]>([
    {
      id: 'doc-1',
      name: 'company_policy.md',
      sizeBytes: 14200,
      type: 'Markdown',
      uploadedAt: '2026-09-14 10:30',
      chunksCount: 8,
      status: 'indexed'
    },
    {
      id: 'doc-2',
      name: 'warranty_terms.txt',
      sizeBytes: 8900,
      type: 'Plain Text',
      uploadedAt: '2026-09-14 11:15',
      chunksCount: 5,
      status: 'indexed'
    },
    {
      id: 'doc-3',
      name: 'developer_guide.md',
      sizeBytes: 32400,
      type: 'Markdown',
      uploadedAt: '2026-09-14 12:40',
      chunksCount: 19,
      status: 'indexed'
    }
  ]);

  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFileUpload = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    // Max 10MB quota check
    if (file.size > 10 * 1024 * 1024) {
      setUploadFeedback(`File exceeds 10MB quota (${(file.size / (1024 * 1024)).toFixed(1)}MB). Please choose a smaller file.`);
      return;
    }

    const validExtensions = ['.pdf', '.docx', '.txt', '.md'];
    const hasValidExt = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
    if (!hasValidExt) {
      setUploadFeedback(`Unsupported file type. Supported: ${validExtensions.join(', ')}`);
      return;
    }

    const newDoc: ManagedDocument = {
      id: `doc-${Date.now()}`,
      name: file.name,
      sizeBytes: file.size,
      type: file.name.endsWith('.pdf') ? 'PDF' : file.name.endsWith('.docx') ? 'DOCX' : file.name.endsWith('.md') ? 'Markdown' : 'Plain Text',
      uploadedAt: new Date().toISOString().replace('T', ' ').slice(0, 16),
      chunksCount: Math.max(1, Math.round(file.size / 1500)),
      status: 'indexed'
    };

    setDocuments(prev => [newDoc, ...prev]);
    setUploadFeedback(`Successfully uploaded and indexed "${file.name}" with dense vector embeddings.`);
    setTimeout(() => setUploadFeedback(null), 5000);
  };

  const handleDelete = (id: string) => {
    setDocuments(prev => prev.filter(d => d.id !== id));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Header */}
      <div>
        <h2>Knowledge Base & Document RAG</h2>
        <p style={{ fontSize: '0.9rem', marginTop: '0.25rem' }}>
          Upload local documents to ground SenseAI answers with verified facts and citations.
        </p>
      </div>

      {/* Upload Zone */}
      <div
        className="panel"
        style={{
          border: isDragging ? '2px dashed var(--color-voice)' : '2px dashed var(--border-subtle)',
          textAlign: 'center',
          padding: '2.5rem 1.5rem',
          cursor: 'pointer',
          background: isDragging ? 'var(--color-voice-glow)' : 'var(--bg-surface)'
        }}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFileUpload(e.dataTransfer.files);
        }}
        onClick={() => document.getElementById('file-upload-input')?.click()}
      >
        <input
          id="file-upload-input"
          type="file"
          accept=".pdf,.docx,.txt,.md"
          style={{ display: 'none' }}
          onChange={(e) => handleFileUpload(e.target.files)}
        />
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'var(--color-voice-glow)', color: 'var(--color-voice)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem auto' }}>
          <Upload size={22} />
        </div>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '0.35rem' }}>Drop your knowledge documents here</h3>
        <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
          Supports PDF, DOCX, TXT, and Markdown files up to 10MB per document.
        </p>
      </div>

      {/* Feedback message */}
      {uploadFeedback && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', padding: '0.85rem 1.25rem', borderRadius: 'var(--radius-sm)', background: uploadFeedback.includes('exceeds') || uploadFeedback.includes('Unsupported') ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)', color: uploadFeedback.includes('exceeds') || uploadFeedback.includes('Unsupported') ? 'var(--color-danger)' : 'var(--color-success)', border: '1px solid currentColor', fontSize: '0.88rem' }}>
          {uploadFeedback.includes('exceeds') || uploadFeedback.includes('Unsupported') ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{uploadFeedback}</span>
        </div>
      )}

      {/* Documents Table */}
      {documents.length === 0 ? (
        <div className="panel" style={{ textAlign: 'center', padding: '3rem 1.5rem' }}>
          <Database size={32} style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }} />
          <h3 style={{ marginBottom: '0.5rem' }}>Ground your assistant with local facts</h3>
          <p style={{ fontSize: '0.9rem', maxWidth: '440px', margin: '0 auto 1.5rem auto' }}>
            Upload company policies, operational manuals, or personal notes to enable factual answers with source citations.
          </p>
        </div>
      ) : (
        <div className="panel" style={{ padding: '0', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Indexed Documents ({documents.length})</span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>FAISS Vector Store: Dense Inner-Product (384-d)</span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>
                  <th style={{ padding: '0.75rem 1.25rem' }}>Document Name</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Type</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Size</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Chunks</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 1.25rem', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.85rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                      <FileText size={16} style={{ color: 'var(--color-voice)' }} />
                      <span style={{ fontWeight: 500 }}>{doc.name}</span>
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary)' }}>{doc.type}</td>
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{formatBytes(doc.sizeBytes)}</td>
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{doc.chunksCount} chunks</td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', color: 'var(--color-success)', fontSize: '0.8rem' }}>
                        <CheckCircle2 size={13} />
                        Indexed
                      </span>
                    </td>
                    <td style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>
                      <button
                        className="btn-icon"
                        style={{ width: '28px', height: '28px', display: 'inline-flex', color: 'var(--text-muted)' }}
                        onClick={() => handleDelete(doc.id)}
                        title="Delete Document"
                        aria-label={`Delete ${doc.name}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
