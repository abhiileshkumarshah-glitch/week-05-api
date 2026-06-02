## Week 5 Reflection

1. What is the difference between the system prompt and the user message?

The system prompt gives the AI instructions about its role, behavior, tone, and rules. The user message is the actual question or request typed by the user. This separation matters because the system prompt controls how the AI should behave, while the user message changes during the conversation.

2. What happened when you changed the system prompt in Part 4?

When I changed the system prompt, the assistant's tone and response style changed. A more opinionated prompt made the answer sound stronger. A structured prompt made the recommendations cleaner and easier to read. A restricted prompt kept the assistant focused only on books.

3. Name one situation where using AI in an app could cause harm, and how you would mitigate it.

AI could give incorrect or misleading book information or recommendations. I would mitigate this by keeping the responses concise, letting users verify book details, and avoiding presenting AI responses as guaranteed facts.

4. If you had infinite Claude API credits, what AI feature would you add to this book tracker? Describe it technically.

I would add an AI reading coach. It would analyze the user's saved books, ratings, reading status, and favorite authors from the database. Then it would generate personalized reading plans, book summaries, and monthly recommendations using an AI API.

Note: I do not have a paid Claude API key, so I implemented real API key handling and used Gemini API as an alternative free model. The API key is stored in `.env` and is not hardcoded in the code.
