## Week 5 Reflection

1. What is the difference between the system prompt and the user message?

The system prompt gives the AI instructions about its role, behavior, tone, and rules. The user message is the question or request typed by the user. This separation matters because the system prompt controls how the AI should behave, while the user message changes during the conversation.

2. What happened when you changed the system prompt in Part 4?

When I changed the system prompt, the assistant's style and format changed. A more opinionated prompt made the response stronger, a structured prompt made the response cleaner, and a restricted prompt kept the assistant focused only on books.

3. Name one situation where using AI in an app could cause harm, and how you would mitigate it.

AI could give incorrect book information or misleading recommendations. I would reduce this risk by showing that AI responses may not always be perfect and by allowing users to verify book details.

4. If you had infinite Claude API credits, what AI feature would you add to this book tracker? Describe it technically.

I would add an AI reading coach. It would analyze the user's saved books, ratings, and reading status from the database, then generate monthly reading plans, summaries, and personalized recommendations.

Note: I built the AI endpoints and frontend chat UI. Since I did not have active Anthropic API credits/key, I used a demo fallback response to test the full app flow.