import { useState, useEffect } from 'react';
import { Flame, Search, Skull, Settings } from 'lucide-react';
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

// API Key service labels for display
const API_LABELS: Record<string, string> = {
  brave_search: "Brave Search (2000/месяц)",
  exa_ai: "Exa.ai (1000/месяц)",
  hunter_io: "Hunter.io (25/месяц)",
  hibp: "Have I Been Pwned",
  shodan: "Shodan (100/месяц)",
  fullcontact: "FullContact",
  clearbit: "Clearbit (50/месяц)",
  social_searcher: "Social Searcher (100/день)"
};

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

  // Settings Modal State
  const [showSettings, setShowSettings] = useState(false);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [services, setServices] = useState<string[]>([]);
  const [savingKeys, setSavingKeys] = useState(false);

  // Load API keys on mount
  useEffect(() => {
    fetch('/api/keys')
      .then(res => res.json())
      .then(data => {
        setApiKeys(data.keys || {});
        setServices(data.services || []);
      })
      .catch(err => console.log('Failed to load keys:', err));
  }, []);

  // Save API keys
  const saveApiKeys = async () => {
    setSavingKeys(true);
    try {
      const res = await fetch('/api/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiKeys)
      });
      if (res.ok) {
        setShowSettings(false);
      }
    } catch (err) {
      console.log('Failed to save keys:', err);
    }
    setSavingKeys(false);
  };

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
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="status">
            {isThinking ? (
              <span style={{ color: 'var(--primary)', fontWeight: 'bold' }}>HUNTING...</span>
            ) : (
              <span style={{ color: 'var(--text-muted)' }}>IDLE</span>
            )}
          </div>
          <button
            onClick={() => setShowSettings(true)}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.5rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center'
            }}
            title="API Settings"
          >
            <Settings size={20} color="var(--text-muted)" />
          </button>
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

                    {/* Digital Footprint */}
                    {parsed.digital_footprint && (
                      <div style={{ background: 'rgba(255, 69, 0, 0.05)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px border var(--border-subtle)' }}>
                        <h4 style={{ color: 'var(--primary)', marginBottom: '0.75rem', textTransform: 'uppercase', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Skull size={16} /> Digital Footprint
                        </h4>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                          {parsed.digital_footprint.emails?.length > 0 && (
                            <div>
                              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Emails</div>
                              {parsed.digital_footprint.emails.map((e: string, i: number) => <div key={i} style={{ color: '#4ade80' }}>{e}</div>)}
                            </div>
                          )}
                          {parsed.digital_footprint.phones?.length > 0 && (
                            <div>
                              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Phones</div>
                              {parsed.digital_footprint.phones.map((p: string, i: number) => <div key={i} style={{ color: '#60a5fa' }}>{p}</div>)}
                            </div>
                          )}
                          {parsed.digital_footprint.social_links?.length > 0 && (
                             <div style={{ gridColumn: '1 / -1' }}>
                               <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Social Profiles</div>
                               <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.25rem' }}>
                                 {parsed.digital_footprint.social_links.map((link: string, i: number) => (
                                   <a key={i} href={link} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', fontSize: '0.9rem' }}>
                                     {new URL(link).hostname.replace('www.', '')}
                                   </a>
                                 ))}
                               </div>
                             </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Personality Analysis (if merged) */}
                    {parsed.personality_analysis && (
                      <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.5rem' }}>
                        <h4 style={{ color: '#a855f7', marginBottom: '1rem', textTransform: 'uppercase', fontSize: '0.9rem' }}>Psychological Profile</h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                          <div style={{ background: '#111', padding: '1rem', borderRadius: '8px' }}>
                            <div style={{ color: '#a855f7', fontWeight: 'bold' }}>Type: {parsed.personality_analysis.personality_type?.value}</div>
                            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                              Evidence: {parsed.personality_analysis.personality_type?.source_evidence}
                            </div>
                          </div>
                          
                          {parsed.personality_analysis.summary && (
                            <div style={{ fontStyle: 'italic', color: '#ccc', borderLeft: '2px solid #a855f7', paddingLeft: '1rem' }}>
                              "{parsed.personality_analysis.summary}"
                            </div>
                          )}
                          
                          {parsed.personality_analysis.red_flags?.length > 0 && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '1rem', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                              <div style={{ color: '#f87171', fontWeight: 'bold', fontSize: '0.8rem', marginBottom: '0.5rem' }}>RED FLAGS</div>
                              {parsed.personality_analysis.red_flags.map((flag: any, i: number) => (
                                <div key={i} style={{ marginBottom: '0.5rem' }}>
                                  • {flag.flag} <br/>
                                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Ref: {flag.source_evidence}</span>
                                </div>
                              ))}
                            </div>
                          )}
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

      {/* Settings Modal */}
      {showSettings && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '2rem',
            width: '90%',
            maxWidth: '500px',
            maxHeight: '80vh',
            overflow: 'auto'
          }}>
            <h2 style={{ marginBottom: '1.5rem', color: 'var(--primary)' }}>⚙️ API Keys</h2>
            <p style={{ marginBottom: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Добавь ключи для турбо-режима. Без ключей поиск идёт через DuckDuckGo (бесплатно).
            </p>

            {services.map(service => (
              <div key={service} className="input-group" style={{ marginBottom: '1rem' }}>
                <label className="label" style={{ fontSize: '0.85rem' }}>
                  {API_LABELS[service] || service}
                </label>
                <input
                  type="password"
                  className="input"
                  placeholder="Введи API ключ..."
                  value={apiKeys[service] || ''}
                  onChange={(e) => setApiKeys(prev => ({ ...prev, [service]: e.target.value }))}
                  style={{ fontSize: '0.9rem' }}
                />
              </div>
            ))}

            <div style={{ display: 'flex', gap: '1rem', marginTop: '1.5rem' }}>
              <button
                className="btn"
                onClick={saveApiKeys}
                disabled={savingKeys}
                style={{ flex: 1 }}
              >
                {savingKeys ? 'Сохраняю...' : '💾 Сохранить'}
              </button>
              <button
                className="btn"
                onClick={() => setShowSettings(false)}
                style={{ flex: 1, background: 'transparent', border: '1px solid var(--border-subtle)' }}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
