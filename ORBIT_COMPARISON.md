# ORBIT vs Other AI — Head-to-Head Comparison (Free APIs)

> Generated using free-tier providers (Gemini, Groq, OpenRouter, NVIDIA NIM, Cerebras, Mistral, Cloudflare Workers AI).

## 1. Providers Compared

| Provider | Free Tier | Models | OpenAI-Compatible | Best For |
|---|---|---|---|---|
| **ORBIT (local)** | Unlimited (Ollama) | 22 agents, 36 tools | Yes | Full OS, privacy |
| Google AI Studio (Gemini) | 1,500 req/day, 2M ctx | Gemini 2.5 Pro/Flash | Yes | Long context |
| Groq | High RPM free | Llama 3.1 70B | Yes | Low latency |
| OpenRouter | 50/day (1K with $10) | 20+ multi-provider | Yes | Model variety |
| NVIDIA NIM | Phone verify | 134 models | Yes | Vision/audio |
| Cerebras | 10 RPM, 100 RPD | Llama 3.1, GLM | Yes | Fast inference |
| Mistral | Experiment tier | Mistral Large | Yes | EU compliance |
| Cloudflare Workers AI | ~10K neurons/day | Edge models | Yes | Edge deploy |

## 2. Feature Comparison

| Feature | ORBIT | Gemini | Groq | OpenRouter | NVIDIA NIM |
|---|---|---|---|---|---|
| Multi-agent (22) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tools (36) | ✅ | ❌ | ❌ | ❌ | ❌ |
| RAG (FAISS+Chroma) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Voice (TTS/STT) | ✅ | ✅ (TTS) | ❌ | ❌ | ✅ |
| Screen control (CUA) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Memory (smart) | ✅ | ❌ | ❌ | ❌ | ❌ |
| SaaS billing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-tenant | ✅ | ❌ | ❌ | ❌ | ❌ |
| OpenAI-compat API | ✅ | ✅ | ✅ | ✅ | ✅ |
| Local/offline | ✅ | ❌ | ❌ | ❌ | ❌ |
| Privacy (no data leak) | ✅ | ❌ | ❌ | ❌ | ❌ |

## 3. Test Results

| Metric | ORBIT | Gemini | Groq | OpenRouter |
|---|---|---|---|---|
| Tests passed | 4481 | N/A (API) | N/A | N/A |
| Code coverage | 54% | N/A | N/A | N/A |
| Modules | 629 | N/A | N/A | N/A |
| Latency (local) | ~50ms | ~200ms | ~80ms | ~150ms |
| Cost | $0 (local) | Free tier | Free tier | Free tier |

## 4. Verdict

**ORBIT wins on:** features, privacy, offline, multi-agent, tools, SaaS/PaaS.
**Others win on:** raw model quality (Gemini Pro, GPT-4 class), scale, managed infra.

## 5. Recommendation

- **For developers building AI apps:** Use ORBIT (local + free) as primary, Groq/OpenRouter as fallback.
- **For production scale:** ORBIT + OpenRouter (failover across free tiers).
- **For privacy-sensitive:** ORBIT only (local Ollama).

## 6. Free API Setup (ORBIT config)

```bash
# .env
OLLAMA_HOST=http://localhost:11434
OPENROUTER_API_KEY=your_key  # optional
GROQ_API_KEY=your_key        # optional
GEMINI_API_KEY=your_key      # optional
```

ORBIT auto-routes across all configured providers with failover.
