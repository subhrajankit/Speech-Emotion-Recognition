"""
VoiceSense AI — Hard Evaluation Dataset for Intent Router Gate.
Authored by the same agent, indicative only.

Contains 50 adversarial and edge-case queries (25 'chat', 25 'knowledge_query')
covering:
1. Conversational chat that mentions 'policy', 'warranty', 'rules', or 'handbook'
2. Short, conversational follow-ups ('Why?', 'And then?')
3. General-knowledge questions NOT covered by the knowledge base
4. Conversational Hinglish
5. Subtly phrased knowledge/policy queries without obvious trigger keywords
"""

HARD_EVALUATION_DATASET = [
    # -------------------------------------------------------------------------
    # CLASS 1: CHAT (Ground Truth: "chat") — 25 Examples
    # -------------------------------------------------------------------------
    # Conversational chat mentioning 'policy', 'warranty', 'handbook', 'rules'
    {
        "id": "hard_chat_01",
        "language": "en",
        "query": "My personal policy in life is to always be kind to strangers.",
        "label": "chat",
        "category": "distractor_policy_word",
    },
    {
        "id": "hard_chat_02",
        "language": "en",
        "query": "I have no policy against working late on personal side projects.",
        "label": "chat",
        "category": "distractor_policy_word",
    },
    {
        "id": "hard_chat_03",
        "language": "en",
        "query": "Life comes with no warranty, so we have to enjoy every single day.",
        "label": "chat",
        "category": "distractor_warranty_word",
    },
    {
        "id": "hard_chat_04",
        "language": "en",
        "query": "There is no warranty that tomorrow will be sunny, haha.",
        "label": "chat",
        "category": "distractor_warranty_word",
    },
    {
        "id": "hard_chat_05",
        "language": "en",
        "query": "My dad has a strict handbook about house rules when we visit.",
        "label": "chat",
        "category": "distractor_handbook_word",
    },
    {
        "id": "hard_chat_06",
        "language": "en",
        "query": "I guarantee you that this neighborhood has the best coffee shop.",
        "label": "chat",
        "category": "distractor_guarantee_word",
    },
    {
        "id": "hard_chat_07",
        "language": "en",
        "query": "I need a survival guide to get through this stressful Monday morning.",
        "label": "chat",
        "category": "distractor_guide_word",
    },
    {
        "id": "hard_chat_08",
        "language": "hi-Latn",
        "query": "Meri personal policy simple hai, hamesha sach bolo aur khush raho.",
        "label": "chat",
        "category": "distractor_hinglish_policy",
    },
    {
        "id": "hard_chat_09",
        "language": "hi-Latn",
        "query": "Zindagi ki koi warranty nahi hoti mere bhai.",
        "label": "chat",
        "category": "distractor_hinglish_warranty",
    },
    {
        "id": "hard_chat_10",
        "language": "hi",
        "query": "मेरी जिंदगी का एक ही नियम है, कभी किसी का दिल मत दुखाओ।",
        "label": "chat",
        "category": "distractor_hindi_rule",
    },
    # Short conversational follow-ups
    {
        "id": "hard_chat_11",
        "language": "en",
        "query": "Why?",
        "label": "chat",
        "category": "short_followup",
    },
    {
        "id": "hard_chat_12",
        "language": "en",
        "query": "What about that?",
        "label": "chat",
        "category": "short_followup",
    },
    {
        "id": "hard_chat_13",
        "language": "en",
        "query": "Tell me more about it.",
        "label": "chat",
        "category": "short_followup",
    },
    {
        "id": "hard_chat_14",
        "language": "en",
        "query": "Are you sure about that?",
        "label": "chat",
        "category": "short_followup",
    },
    {
        "id": "hard_chat_15",
        "language": "hi-Latn",
        "query": "Samjha nahi, fir se batao yaar.",
        "label": "chat",
        "category": "short_followup_hinglish",
    },
    {
        "id": "hard_chat_16",
        "language": "hi-Latn",
        "query": "Achha aisa hai kya? Theek hai.",
        "label": "chat",
        "category": "short_followup_hinglish",
    },
    {
        "id": "hard_chat_17",
        "language": "hi",
        "query": "फिर आगे क्या हुआ?",
        "label": "chat",
        "category": "short_followup_hindi",
    },
    # General knowledge (out-of-scope for company KB)
    {
        "id": "hard_chat_18",
        "language": "en",
        "query": "Who was the first president of the United States?",
        "label": "chat",
        "category": "general_knowledge",
    },
    {
        "id": "hard_chat_19",
        "language": "en",
        "query": "What is the capital city of Australia?",
        "label": "chat",
        "category": "general_knowledge",
    },
    {
        "id": "hard_chat_20",
        "language": "en",
        "query": "How far is the Moon from Earth in kilometers?",
        "label": "chat",
        "category": "general_knowledge",
    },
    {
        "id": "hard_chat_21",
        "language": "en",
        "query": "Can you explain how photosynthesis works in green plants?",
        "label": "chat",
        "category": "general_knowledge",
    },
    {
        "id": "hard_chat_22",
        "language": "en",
        "query": "What does quantum superposition mean in simple terms?",
        "label": "chat",
        "category": "general_knowledge",
    },
    {
        "id": "hard_chat_23",
        "language": "hi",
        "query": "सौर मंडल का सबसे बड़ा ग्रह कौन सा है?",
        "label": "chat",
        "category": "general_knowledge_hindi",
    },
    {
        "id": "hard_chat_24",
        "language": "hi-Latn",
        "query": "Duniya ka sabse uncha mountain kaun sa hai?",
        "label": "chat",
        "category": "general_knowledge_hinglish",
    },
    {
        "id": "hard_chat_25",
        "language": "en",
        "query": "Can you write a short poem about autumn leaves falling?",
        "label": "chat",
        "category": "creative_chat",
    },

    # -------------------------------------------------------------------------
    # CLASS 2: KNOWLEDGE QUERY (Ground Truth: "knowledge_query") — 25 Examples
    # -------------------------------------------------------------------------
    # Ambiguous or non-keyword-heavy queries targeting document store
    {
        "id": "hard_know_01",
        "language": "en",
        "query": "How many days do I get after purchasing before I can no longer return this?",
        "label": "knowledge_query",
        "category": "implicit_policy_refund",
    },
    {
        "id": "hard_know_02",
        "language": "en",
        "query": "If my laptop screen cracks accidentally, will the company repair it for free?",
        "label": "knowledge_query",
        "category": "implicit_policy_warranty",
    },
    {
        "id": "hard_know_03",
        "language": "en",
        "query": "Can you look into our files regarding parental leave duration?",
        "label": "knowledge_query",
        "category": "file_lookup",
    },
    {
        "id": "hard_know_04",
        "language": "en",
        "query": "What is the official procedure when an employee decides to resign?",
        "label": "knowledge_query",
        "category": "implicit_hr_procedure",
    },
    {
        "id": "hard_know_05",
        "language": "en",
        "query": "Show me what the compliance guidelines say about accepting gifts from vendors.",
        "label": "knowledge_query",
        "category": "compliance_guidelines",
    },
    {
        "id": "hard_know_06",
        "language": "en",
        "query": "What is the maximum expense amount an employee can claim for an airport taxi?",
        "label": "knowledge_query",
        "category": "expense_limits",
    },
    {
        "id": "hard_know_07",
        "language": "hi-Latn",
        "query": "Kya company remote workers ko electricity bill reimburse karti hai?",
        "label": "knowledge_query",
        "category": "hinglish_reimbursement",
    },
    {
        "id": "hard_know_08",
        "language": "hi-Latn",
        "query": "Sickness ke case mein kitne din ki leave milti hai handbook ke mutabiq?",
        "label": "knowledge_query",
        "category": "hinglish_leave",
    },
    {
        "id": "hard_know_09",
        "language": "hi-Latn",
        "query": "Agar product defective deliver hua toh replacement kitne din mein milega?",
        "label": "knowledge_query",
        "category": "hinglish_defective_return",
    },
    {
        "id": "hard_know_10",
        "language": "en",
        "query": "What does section 4.2 say about intellectual property rights?",
        "label": "knowledge_query",
        "category": "section_citation",
    },
    {
        "id": "hard_know_11",
        "language": "en",
        "query": "Where can I read about our server failover and maintenance protocols?",
        "label": "knowledge_query",
        "category": "maintenance_doc",
    },
    {
        "id": "hard_know_12",
        "language": "en",
        "query": "According to the contract, what is the notice period required for termination?",
        "label": "knowledge_query",
        "category": "contract_clause",
    },
    {
        "id": "hard_know_13",
        "language": "en",
        "query": "Check if our company covers dental treatments under health insurance.",
        "label": "knowledge_query",
        "category": "insurance_coverage",
    },
    {
        "id": "hard_know_14",
        "language": "en",
        "query": "Is there an overtime compensation policy for weekend deployments?",
        "label": "knowledge_query",
        "category": "overtime_policy",
    },
    {
        "id": "hard_know_15",
        "language": "hi",
        "query": "दस्तावेज़ के अनुसार मैटरनिटी लीव के क्या नियम हैं?",
        "label": "knowledge_query",
        "category": "hindi_doc_query",
    },
    {
        "id": "hard_know_16",
        "language": "hi",
        "query": "रिफंड प्रोसेस होने में अधिकतम कितना समय लगता है?",
        "label": "knowledge_query",
        "category": "hindi_refund_query",
    },
    {
        "id": "hard_know_17",
        "language": "hi",
        "query": "कंपनी की गाइडलाइंस में डेटा सिक्योरिटी के क्या नियम दिए गए हैं?",
        "label": "knowledge_query",
        "category": "hindi_security_doc",
    },
    {
        "id": "hard_know_18",
        "language": "en",
        "query": "Do we have a specific policy document for work from home allowances?",
        "label": "knowledge_query",
        "category": "wfh_policy_doc",
    },
    {
        "id": "hard_know_19",
        "language": "en",
        "query": "What does the employee handbook state about jury duty leave?",
        "label": "knowledge_query",
        "category": "handbook_jury_duty",
    },
    {
        "id": "hard_know_20",
        "language": "en",
        "query": "What are the exact system specifications required to run this software locally?",
        "label": "knowledge_query",
        "category": "technical_specs",
    },
    {
        "id": "hard_know_21",
        "language": "en",
        "query": "Check our security guidelines for password rotation intervals.",
        "label": "knowledge_query",
        "category": "security_guidelines",
    },
    {
        "id": "hard_know_22",
        "language": "en",
        "query": "According to the terms of service, can accounts be suspended without notice?",
        "label": "knowledge_query",
        "category": "tos_terms",
    },
    {
        "id": "hard_know_23",
        "language": "hi",
        "query": "वारंटी की क्या शर्तें दी गई हैं नियम पुस्तिका में?",
        "label": "knowledge_query",
        "category": "hindi_warranty_terms",
    },
    {
        "id": "hard_know_24",
        "language": "hi-Latn",
        "query": "Company policy ke according maternity leave kitne months milti hai?",
        "label": "knowledge_query",
        "category": "hinglish_policy_doc",
    },
    {
        "id": "hard_know_25",
        "language": "hi-Latn",
        "query": "Travel reimbursement limit kitni hai according to guidelines?",
        "label": "knowledge_query",
        "category": "hinglish_reimbursement_doc",
    },
]
