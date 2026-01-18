import { useState } from 'react';
import { Flame, Search, Skull } from 'lucide-react';
import './App.css';

// Define the shape of our "Dead Data"
interface TargetProfile {
  name: string;
  city: string;
  country: string;
  phone: string;
  nickname: string;
  other_clues: string;
}

interface AnalysisResult {
  status: string;
  response: string;
  gathered_data: string[];
}

function App() {
  const [profile, setProfile] = useState<TargetProfile>({
    name: '',
    city: '',
    country: '',
    phone: '',
    nickname: '',
    other_clues: ''
  });

  const [isThinking, setIsThinking] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setProfile(prev => ({ ...prev, [name]: value }));
  };

  const startHunt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile.name) return;

    setIsThinking(true);
    setResult(null);
    setError(null);

    try {
      // Connect to our Python Brain via Vite proxy
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ profile }),
      });

      if (!response.ok) {
        throw new Error(`Brain malfunction: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Unknown error occurred');
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <div className="title">
          <Skull size={32} />
          <span>Bakasura</span>
        </div>
        <div className="status">
          {isThinking ? (
            <span style={{ color: 'var(--primary)', fontWeight: 'bold' }}>HUNTING...</span>
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>IDLE</span>
          )}
        </div>
      </header>

      <main>
        {!isThinking && !result && (
          <div className="card">
            <h2 className="label" style={{ fontSize: '1.2rem', color: 'var(--text-main)', marginBottom: '1.5rem' }}>
              Feed the Beast (Target Protocol)
            </h2>
            <form onSubmit={startHunt}>
              <div className="input-group">
                <label className="label">Full Name *</label>
                <input
                  name="name"
                  className="input"
                  placeholder="e.g. John Doe"
                  value={profile.name}
                  onChange={handleInputChange}
                  required
                />
              </div>

              <div className="grid-2">
                <div className="input-group">
                  <label className="label">City</label>
                  <input
                    name="city"
                    className="input"
                    placeholder="e.g. Moscow"
                    value={profile.city}
                    onChange={handleInputChange}
                  />
                </div>
                <div className="input-group">
                  <label className="label">Country</label>
                  <input
                    name="country"
                    className="input"
                    placeholder="e.g. Russia"
                    value={profile.country}
                    onChange={handleInputChange}
                  />
                </div>
              </div>

              <div className="grid-2">
                <div className="input-group">
                  <label className="label">Phone Number</label>
                  <input
                    name="phone"
                    className="input"
                    placeholder="+7..."
                    value={profile.phone}
                    onChange={handleInputChange}
                  />
                </div>
                <div className="input-group">
                  <label className="label">Nickname / Handle</label>
                  <input
                    name="nickname"
                    className="input"
                    placeholder="@username"
                    value={profile.nickname}
                    onChange={handleInputChange}
                  />
                </div>
              </div>

              <div className="input-group">
                <label className="label">Other Clues (Dead Data)</label>
                <textarea
                  name="other_clues"
                  className="input"
                  rows={3}
                  placeholder="Any other details..."
                  value={profile.other_clues}
                  onChange={handleInputChange}
                />
              </div>

              <button type="submit" className="btn" disabled={isThinking}>
                <Flame size={20} />
                INITIATE PROTOCOL
              </button>
            </form>
          </div>
        )}

        {isThinking && (
          <div className="demon-eye-container">
            <div className="demon-eye">
              <div className="pupil"></div>
            </div>
            <p style={{ marginTop: '2rem', color: 'var(--primary)', letterSpacing: '2px' }}>
              CONSUMING DATA...
            </p>
          </div>
        )}

        {result && (
          <div className="results-container">
            <div className="card" style={{ borderColor: 'var(--primary)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <Search color="var(--primary)" />
                <h3 style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>Analysis Complete</h3>
              </div>

              {(() => {
                let parsed;
                const responseContent = typeof result.response === 'string' ? result.response : JSON.stringify(result.response);

                try {
                  // Clean up markdown code blocks if present (just in case backend missed it)
                  let cleanJson = responseContent;
                  if (cleanJson.includes("```json")) {
                    cleanJson = cleanJson.replace(/```json/g, "").replace(/```/g, "");
                  }
                  parsed = JSON.parse(cleanJson);
                } catch (e) {
                  return (
                    <div style={{ color: 'var(--text-main)', fontSize: '1.1rem', lineHeight: '1.6', whiteSpace: 'pre-line' }}>
                      {result.response}
                    </div>
                  );
                }

                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    {/* Status Badge */}
                    <div style={{
                      padding: '0.5rem 1rem',
                      borderRadius: 'var(--radius-sm)',
                      background: parsed.is_person_found ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 0, 0, 0.1)',
                      border: `1px solid ${parsed.is_person_found ? 'green' : 'red'}`,
                      color: parsed.is_person_found ? '#4ade80' : '#f87171',
                      width: 'fit-content',
                      fontWeight: 'bold'
                    }}>
                      {parsed.is_person_found ? 'TARGET IDENTIFIED' : 'TARGET NOT FOUND / AMBIGUOUS'}
                    </div>

                    {/* Facts */}
                    {Array.isArray(parsed.facts) && parsed.facts.length > 0 && (
                      <div>
                        <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', fontSize: '0.9rem' }}>Established Facts</h4>
                        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {parsed.facts.map((fact: string, i: number) => (
                            <li key={i} style={{ display: 'flex', gap: '0.5rem' }}>
                              <span style={{ color: 'var(--primary)' }}>➤</span>
                              {fact}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Matched Sources */}
                    {Array.isArray(parsed.matched_sources) && parsed.matched_sources.length > 0 && (
                      <div>
                        <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', fontSize: '0.9rem' }}>Direct Matches / Evidence</h4>
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                          {parsed.matched_sources.map((src: any, i: number) => (
                            <a
                              key={i}
                              href={src.url}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                display: 'block',
                                padding: '1rem',
                                background: '#1a1a1a',
                                borderRadius: 'var(--radius-md)',
                                border: '1px solid var(--border-subtle)',
                                textDecoration: 'none'
                              }}
                            >
                              <div style={{ fontWeight: 'bold', color: 'var(--primary)', marginBottom: '0.25rem' }}>{src.title}</div>
                              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>{src.url}</div>
                              {src.reason && (
                                <div style={{ fontSize: '0.9rem', color: '#ccc', fontStyle: 'italic', borderLeft: '2px solid var(--primary)', paddingLeft: '0.5rem' }}>
                                  "{src.reason}"
                                </div>
                              )}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Uncertain / Notes */}
                    {((Array.isArray(parsed.uncertain) && parsed.uncertain.length > 0) || parsed.notes) && (
                      <div style={{ background: '#151515', padding: '1rem', borderRadius: 'var(--radius-md)' }}>
                        <h4 style={{ color: '#eab308', marginBottom: '0.5rem', fontSize: '0.9rem' }}>⚠️ Uncertainty & Notes</h4>
                        {Array.isArray(parsed.uncertain) && parsed.uncertain.map((u: string, i: number) => (
                          <div key={i} style={{ marginBottom: '0.5rem' }}>• {u}</div>
                        ))}
                        {parsed.notes && <div style={{ marginTop: '0.5rem', fontStyle: 'italic' }}>Note: {parsed.notes}</div>}
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>

            {result.gathered_data && result.gathered_data.length > 0 && (
              <div className="logs">
                <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.85rem' }}>RAW INTEL FEED:</h4>
                {result.gathered_data.map((log, i) => (
                  <div key={i} className="log-entry">{log}</div>
                ))}
              </div>
            )}

            <button
              className="btn"
              style={{ marginTop: '2rem', background: 'transparent', border: '1px solid var(--border-subtle)' }}
              onClick={() => setResult(null)}
            >
              NEW HUNT
            </button>
          </div>
        )}

        {error && (
          <div className="card" style={{ marginTop: '1rem', borderColor: 'red', color: 'red' }}>
            ERROR: {error}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
