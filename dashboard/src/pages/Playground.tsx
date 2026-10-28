import React, { useState } from 'react';
import Layout from '../components/Layout';
import axios from 'axios';
import { Play, Shield, AlertTriangle, CheckCircle, Zap } from 'lucide-react';
import { API_BASE_URL } from '../utils/api';

interface AttackPreset {
    name: string;
    description: string;
    tier: 'SAFE' | 'LOW_RISK' | 'MEDIUM_RISK' | 'HIGH_RISK' | 'CRITICAL';
    badgeColor: string;
    query: string;
}

const PRESETS: AttackPreset[] = [
    {
        name: "Safe Baseline",
        description: "Normal production query",
        tier: "SAFE",
        badgeColor: "bg-green-100 text-green-700 hover:bg-green-200 border-green-300",
        query: `query GetUserProfile {
  user(id: "usr_42") {
    id
    name
    posts(limit: 5) {
      id
      title
    }
  }
}`
    },
    {
        name: "SQL Injection",
        description: "Bypasses authentication via SQL injection in arguments",
        tier: "CRITICAL",
        badgeColor: "bg-red-100 text-red-700 hover:bg-red-200 border-red-300",
        query: `query ExploitAuthentication {
  user(name: "' OR '1'='1' UNION SELECT * FROM credentials--") {
    id
    email
  }
}`
    },
    {
        name: "Depth Bomb (DoS)",
        description: "12 levels of recursive query nesting",
        tier: "HIGH_RISK",
        badgeColor: "bg-orange-100 text-orange-700 hover:bg-orange-200 border-orange-300",
        query: `query NestedDepthBomb {
  a {
    b {
      c {
        d {
          e {
            f {
              g {
                h {
                  i {
                    j {
                      k {
                        l
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}`
    },
    {
        name: "Circular Fragment Loop",
        description: "Infinite expansion loop between recursive fragments",
        tier: "CRITICAL",
        badgeColor: "bg-red-100 text-red-700 hover:bg-red-200 border-red-300",
        query: `query CircularLoopAttack {
  user(id: "1") {
    ...FragmentA
  }
}

fragment FragmentA on User {
  id
  ...FragmentB
}

fragment FragmentB on User {
  name
  ...FragmentA
}`
    },
    {
        name: "Schema Enumeration",
        description: "Full introspection probing types & schema",
        tier: "MEDIUM_RISK",
        badgeColor: "bg-yellow-100 text-yellow-700 hover:bg-yellow-200 border-yellow-300",
        query: `query IntrospectEntireSchema {
  __schema {
    types {
      name
      fields {
        name
        type {
          name
        }
      }
    }
  }
}`
    },
    {
        name: "Alias Overload (Batch)",
        description: "8 parallel resolver executions via aliases",
        tier: "HIGH_RISK",
        badgeColor: "bg-orange-100 text-orange-700 hover:bg-orange-200 border-orange-300",
        query: `query AliasFlood {
  u1: user(id: "1") { id email }
  u2: user(id: "2") { id email }
  u3: user(id: "3") { id email }
  u4: user(id: "4") { id email }
  u5: user(id: "5") { id email }
  u6: user(id: "6") { id email }
  u7: user(id: "7") { id email }
  u8: user(id: "8") { id email }
}`
    },
    {
        name: "@cost Directive Weight",
        description: "Explicit heavy computation resolver cost weights",
        tier: "HIGH_RISK",
        badgeColor: "bg-purple-100 text-purple-700 hover:bg-purple-200 border-purple-300",
        query: `query HighCostCalculations {
  heavyAnalytics @cost(weight: 2500) {
    reportData @cost(weight: 1500)
    auditLog @cost(weight: 1500)
  }
}`
    }
];

const Playground: React.FC = () => {
    const [query, setQuery] = useState<string>(PRESETS[0].query);
    const [response, setResponse] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const handleRunQuery = async (queryText?: string) => {
        const textToRun = queryText !== undefined ? queryText : query;
        setLoading(true);
        try {
            const res = await axios.post(`${API_BASE_URL}/graphql-proxy`, {
                query: textToRun
            });
            setResponse(res.data);
        } catch (error: any) {
            setResponse(error.response?.data || { error: "Request failed" });
        } finally {
            setLoading(false);
        }
    };

    return (
        <Layout>
            <div className="flex justify-between items-center mb-4">
                <h1 className="text-2xl font-bold text-slate-800">Query Playground & Threat Simulator</h1>
            </div>

            {/* 1-Click Simulation Presets Bar */}
            <div className="mb-4 bg-white p-3 rounded-lg shadow-sm border border-slate-200">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center space-x-1">
                    <Zap size={14} className="text-amber-500" />
                    <span>1-Click Security Simulation Presets</span>
                </div>
                <div className="flex flex-wrap gap-2">
                    {PRESETS.map((p) => (
                        <button
                            key={p.name}
                            onClick={() => {
                                setQuery(p.query);
                                handleRunQuery(p.query);
                            }}
                            className={`px-2.5 py-1 text-xs font-semibold rounded border transition-all ${p.badgeColor}`}
                            title={p.description}
                        >
                            {p.name}
                        </button>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-17rem)]">
                {/* Input Section */}
                <div className="flex flex-col bg-white rounded-lg shadow overflow-hidden">
                    <div className="bg-slate-100 px-4 py-2 border-b border-slate-200 flex justify-between items-center">
                        <span className="text-sm font-medium text-slate-600">GraphQL Query Editor</span>
                        <button
                            onClick={() => handleRunQuery()}
                            disabled={loading}
                            className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors disabled:opacity-50"
                        >
                            <Play size={14} />
                            <span>{loading ? 'Running...' : 'Run Query'}</span>
                        </button>
                    </div>
                    <textarea
                        className="flex-1 p-4 font-mono text-sm resize-none focus:outline-none"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        spellCheck={false}
                    />
                </div>

                {/* Output Section */}
                <div className="flex flex-col bg-white rounded-lg shadow overflow-hidden">
                    <div className="bg-slate-100 px-4 py-2 border-b border-slate-200">
                        <span className="text-sm font-medium text-slate-600">Response & Security Analysis</span>
                    </div>
                    <div className="flex-1 p-4 overflow-auto bg-slate-50">
                        {response ? (
                            <div className="space-y-6">
                                {/* Security Decision */}
                                {response.extensions?.security && (
                                    <div className={`p-4 rounded-lg border ${response.extensions.security.decision === 'BLOCK' ? 'bg-red-50 border-red-200' :
                                        response.extensions.security.decision === 'THROTTLE' ? 'bg-yellow-50 border-yellow-200' :
                                            'bg-green-50 border-green-200'
                                        }`}>
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="flex items-center space-x-2">
                                                {response.extensions.security.decision === 'BLOCK' ? <Shield className="text-red-500" /> :
                                                    response.extensions.security.decision === 'THROTTLE' ? <AlertTriangle className="text-yellow-500" /> :
                                                        <CheckCircle className="text-green-500" />}
                                                <span className="font-bold text-lg">
                                                    {response.extensions.security.decision}
                                                </span>
                                            </div>
                                            {/* Risk Tier Badge */}
                                            <span className={`px-3 py-1 text-sm font-bold rounded-full ${response.extensions.security.risk_tier === 'CRITICAL' ? 'bg-red-200 text-red-800' :
                                                response.extensions.security.risk_tier === 'HIGH_RISK' ? 'bg-orange-200 text-orange-800' :
                                                    response.extensions.security.risk_tier === 'MEDIUM_RISK' ? 'bg-yellow-200 text-yellow-800' :
                                                        response.extensions.security.risk_tier === 'LOW_RISK' ? 'bg-blue-200 text-blue-800' :
                                                            'bg-green-200 text-green-800'
                                                }`}>
                                                {response.extensions.security.risk_tier || 'SAFE'}
                                            </span>
                                        </div>

                                        {/* Score Overview */}
                                        <div className="grid grid-cols-2 gap-4 text-sm mb-3">
                                            <div>
                                                <span className="text-slate-500">Final Score:</span>
                                                <span className="font-mono font-bold ml-2 text-xl">
                                                    {response.extensions.security.score !== undefined ? response.extensions.security.score.toFixed(1) : '0.0'}
                                                </span>
                                                <span className="text-slate-400">/100</span>
                                            </div>
                                            <div>
                                                <span className="text-slate-500">Latency:</span>
                                                <span className="font-mono font-bold ml-2">
                                                    {response.extensions.security.latency_ms !== undefined ? response.extensions.security.latency_ms.toFixed(2) : '0.00'}ms
                                                </span>
                                            </div>
                                        </div>

                                        {/* Model Scores */}
                                        {response.extensions.security.model_scores && (
                                            <div className="border-t pt-3">
                                                <h5 className="text-xs font-bold text-slate-400 uppercase mb-2">Model Scores</h5>
                                                <div className="grid grid-cols-4 gap-2 text-xs">
                                                    <div className="bg-white p-2 rounded text-center shadow-sm">
                                                        <div className="text-purple-600 font-semibold">Autoencoder</div>
                                                        <div className="font-mono text-lg">{(response.extensions.security.model_scores.autoencoder || 0).toFixed(3)}</div>
                                                    </div>
                                                    <div className="bg-white p-2 rounded text-center shadow-sm">
                                                        <div className="text-blue-600 font-semibold">Random Forest</div>
                                                        <div className="font-mono text-lg">{(response.extensions.security.model_scores.random_forest || 0).toFixed(3)}</div>
                                                    </div>
                                                    <div className="bg-white p-2 rounded text-center shadow-sm">
                                                        <div className="text-green-600 font-semibold">LSTM</div>
                                                        <div className="font-mono text-lg">{(response.extensions.security.model_scores.lstm || 0).toFixed(3)}</div>
                                                    </div>
                                                    <div className="bg-white p-2 rounded text-center shadow-sm">
                                                        <div className="text-orange-600 font-semibold">GNN</div>
                                                        <div className="font-mono text-lg">{(response.extensions.security.model_scores.gnn || 0).toFixed(3)}</div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Explainability Breakdown */}
                                        {response.extensions.security.explanations && response.extensions.security.explanations.length > 0 && (
                                            <div className="border-t pt-3 mt-3">
                                                <h5 className="text-xs font-bold text-slate-400 uppercase mb-2">Threat Explanations</h5>
                                                <div className="space-y-1.5">
                                                    {response.extensions.security.explanations.map((exp: any, idx: number) => (
                                                        <div key={idx} className="text-xs bg-white/80 p-2 rounded border border-slate-200 flex justify-between items-center">
                                                            <span className="font-medium text-slate-700">{exp.description}</span>
                                                            <span className="font-mono text-slate-500 font-bold ml-2">{(exp.score * 100).toFixed(0)}%</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Raw JSON Response */}
                                <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">JSON Response</h4>
                                    <pre className="font-mono text-xs text-slate-700 whitespace-pre-wrap break-all bg-white p-3 rounded border border-slate-200">
                                        {JSON.stringify(response, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                                Select a preset or run a custom query to view real-time security inspection
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </Layout>
    );
};

export default Playground;
