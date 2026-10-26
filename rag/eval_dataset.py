"""
Labelled evaluation dataset for Intent Router Gate (Phase 7).
Contains at least 30 examples per class:
- 35 'chat' examples across English, Hindi, and Hinglish
- 35 'knowledge_query' examples across English, Hindi, and Hinglish
"""

from typing import List, Dict, Any

EVALUATION_DATASET: List[Dict[str, Any]] = [
    # -------------------------------------------------------------
    # Class: CHAT (35 queries)
    # -------------------------------------------------------------
    {"id": 1, "language": "en", "label": "chat", "query": "Hello! How are you doing today?"},
    {"id": 2, "language": "en", "label": "chat", "query": "Good morning, hope you're having a nice day."},
    {"id": 3, "language": "en", "label": "chat", "query": "I feel really stressed out with work lately."},
    {"id": 4, "language": "en", "label": "chat", "query": "Can you tell me a funny joke?"},
    {"id": 5, "language": "en", "label": "chat", "query": "Thank you so much for your help!"},
    {"id": 6, "language": "en", "label": "chat", "query": "What is your favorite color?"},
    {"id": 7, "language": "en", "label": "chat", "query": "I'm going for a walk in the park."},
    {"id": 8, "language": "en", "label": "chat", "query": "Who created you?"},
    {"id": 9, "language": "en", "label": "chat", "query": "What should I eat for dinner tonight?"},
    {"id": 10, "language": "en", "label": "chat", "query": "That's amazing, good job!"},
    {"id": 11, "language": "en", "label": "chat", "query": "I am feeling very happy today."},
    {"id": 12, "language": "en", "label": "chat", "query": "Can we just talk for a while?"},
    {"id": 13, "language": "en", "label": "chat", "query": "Good night, talk to you tomorrow."},
    {"id": 14, "language": "en", "label": "chat", "query": "You're really smart."},
    {"id": 15, "language": "en", "label": "chat", "query": "Never mind, forget I asked."},
    {"id": 16, "language": "hi", "label": "chat", "query": "नमस्ते, आप कैसे हैं?"},
    {"id": 17, "language": "hi", "label": "chat", "query": "सुप्रभात! आज का दिन कैसा रहा?"},
    {"id": 18, "language": "hi", "label": "chat", "query": "मुझे आज बहुत थकान महसूस हो रही है।"},
    {"id": 19, "language": "hi", "label": "chat", "query": "कोई अच्छी सी कविता सुनाओ।"},
    {"id": 20, "language": "hi", "label": "chat", "query": "बहुत-बहुत धन्यवाद आपका।"},
    {"id": 21, "language": "hi", "label": "chat", "query": "क्या तुम मेरे दोस्त बन सकते हो?"},
    {"id": 22, "language": "hi", "label": "chat", "query": "आज मौसम बहुत सुहावना है।"},
    {"id": 23, "language": "hi", "label": "chat", "query": "मुझे बहुत गुस्सा आ रहा है।"},
    {"id": 24, "language": "hi", "label": "chat", "query": "शुभ रात्रि, कल मिलते हैं।"},
    {"id": 25, "language": "hi", "label": "chat", "query": "बस ऐसे ही बात करने का मन था।"},
    {"id": 26, "language": "hi-Latn", "label": "chat", "query": "Hi yaar, kaisa chal raha hai sab?"},
    {"id": 27, "language": "hi-Latn", "label": "chat", "query": "Aaj mera mood thoda off hai."},
    {"id": 28, "language": "hi-Latn", "label": "chat", "query": "Thanks a lot bhai, bohot badhiya!"},
    {"id": 29, "language": "hi-Latn", "label": "chat", "query": "Koi funny joke sunao na please."},
    {"id": 30, "language": "hi-Latn", "label": "chat", "query": "Chalo kal baat karte hain, good night."},
    {"id": 31, "language": "hi-Latn", "label": "chat", "query": "Bhai tu bohot sahi assistant hai."},
    {"id": 32, "language": "hi-Latn", "label": "chat", "query": "Aaj office mein bohot kaam tha, thak gaya hoon."},
    {"id": 33, "language": "hi-Latn", "label": "chat", "query": "Kuch accha gaana suggest karo na."},
    {"id": 34, "language": "hi-Latn", "label": "chat", "query": "Kya haal chaal hai aapke?"},
    {"id": 35, "language": "hi-Latn", "label": "chat", "query": "Main theek hoon, tum sunao."},

    # -------------------------------------------------------------
    # Class: KNOWLEDGE_QUERY (35 queries)
    # -------------------------------------------------------------
    {"id": 36, "language": "en", "label": "knowledge_query", "query": "According to the company policy, what is the refund window?"},
    {"id": 37, "language": "en", "label": "knowledge_query", "query": "What does the employee handbook say about parental leave?"},
    {"id": 38, "language": "en", "label": "knowledge_query", "query": "In the documentation, what are the system requirements for installation?"},
    {"id": 39, "language": "en", "label": "knowledge_query", "query": "Check the server maintenance schedule in the manual."},
    {"id": 40, "language": "en", "label": "knowledge_query", "query": "What is the warranty coverage period mentioned in the document?"},
    {"id": 41, "language": "en", "label": "knowledge_query", "query": "Search the uploaded PDF for the termination clause."},
    {"id": 42, "language": "en", "label": "knowledge_query", "query": "According to the architecture spec, what vector database is used?"},
    {"id": 43, "language": "en", "label": "knowledge_query", "query": "What does section 4 of the guidelines specify about security?"},
    {"id": 44, "language": "en", "label": "knowledge_query", "query": "Look up the maximum reimbursement limit in the travel policy."},
    {"id": 45, "language": "en", "label": "knowledge_query", "query": "How do I reset my credentials according to the user guide?"},
    {"id": 46, "language": "en", "label": "knowledge_query", "query": "What are the API rate limits documented in the developer manual?"},
    {"id": 47, "language": "en", "label": "knowledge_query", "query": "What does the contract state regarding confidentiality obligations?"},
    {"id": 48, "language": "en", "label": "knowledge_query", "query": "In the file, what are the working hours for remote employees?"},
    {"id": 49, "language": "en", "label": "knowledge_query", "query": "Check the policy on sick leave roll-over."},
    {"id": 50, "language": "en", "label": "knowledge_query", "query": "What does the code of conduct document say about gift acceptance?"},
    {"id": 51, "language": "hi", "label": "knowledge_query", "query": "कंपनी की पॉलिसी के अनुसार रिफंड कितने दिनों में मिलता है?"},
    {"id": 52, "language": "hi", "label": "knowledge_query", "query": "दस्तावेज़ में सर्वर मेंटेनेंस का क्या समय दिया गया है?"},
    {"id": 53, "language": "hi", "label": "knowledge_query", "query": "कर्मचारी हैंडबुक में मैटरनिटी लीव के बारे में क्या लिखा है?"},
    {"id": 54, "language": "hi", "label": "knowledge_query", "query": "दिए गए गाइड में पासवर्ड रीसेट करने की क्या प्रक्रिया है?"},
    {"id": 55, "language": "hi", "label": "knowledge_query", "query": "दस्तावेज़ के अनुसार वारंटी की क्या शर्तें हैं?"},
    {"id": 56, "language": "hi", "label": "knowledge_query", "query": "ट्रेवल पॉलिसी में भत्ते की अधिकतम सीमा क्या है?"},
    {"id": 57, "language": "hi", "label": "knowledge_query", "query": "इस फाइल में दिए गए सिक्योरिटी नियमों को चेक करें।"},
    {"id": 58, "language": "hi", "label": "knowledge_query", "query": "मैन्युअल में बताए गए सिस्टम कॉन्फ़िगरेशन क्या हैं?"},
    {"id": 59, "language": "hi", "label": "knowledge_query", "query": "नियम पुस्तिका के अनुसार नोटिस पीरियड कितने महीने का है?"},
    {"id": 60, "language": "hi", "label": "knowledge_query", "query": "कांट्रैक्ट डॉक्यूमेंट में कैंसिलेशन फीस कितनी लिखी है?"},
    {"id": 61, "language": "hi-Latn", "label": "knowledge_query", "query": "Company policy ke according refund kab tak milta hai?"},
    {"id": 62, "language": "hi-Latn", "label": "knowledge_query", "query": "Docs mein check karo ki server maintenance kis time hoti hai?"},
    {"id": 63, "language": "hi-Latn", "label": "knowledge_query", "query": "Employee handbook mein leave policy kya likhi hai?"},
    {"id": 64, "language": "hi-Latn", "label": "knowledge_query", "query": "Document ke hisab se warranty kitne saal ki hai?"},
    {"id": 65, "language": "hi-Latn", "label": "knowledge_query", "query": "Uploaded PDF mein travel allowance ki limit kya hai?"},
    {"id": 66, "language": "hi-Latn", "label": "knowledge_query", "query": "HR manual mein resignation notice period kitna bataya gaya hai?"},
    {"id": 67, "language": "hi-Latn", "label": "knowledge_query", "query": "According to the file, remote work ke kya rules hain?"},
    {"id": 68, "language": "hi-Latn", "label": "knowledge_query", "query": "Is document mein health insurance coverage ke baare mein kya likha hai?"},
    {"id": 69, "language": "hi-Latn", "label": "knowledge_query", "query": "Guidelines document mein security requirements kya hain?"},
    {"id": 70, "language": "hi-Latn", "label": "knowledge_query", "query": "Handbook ke mutabiq overtime pay ka kya rule hai?"},
]
