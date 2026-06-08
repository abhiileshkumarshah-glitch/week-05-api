## Week 6 Reflection

1. What is the key difference between calling an LLM once and using an agent?

Calling an LLM once gives one response from one prompt. An agent can decide to use tools, read tool results, and then continue. In this lab, the agent can update Dune as read, give it 5 stars, and then check what books are currently being read.

2. The agent receives tool results back as "user" role messages. Why does this work?

This works because the model uses the conversation history as context. Tool results become new information that the model can use to decide the final answer. It shows that LLMs need outside information added back into the conversation.

3. What would happen if your tool descriptions were vague or incorrect?

The agent might choose the wrong tool or use the wrong input. For example, if delete_book was not clearly described, the agent might delete a book when the user only wanted to view it.

4. You now use Claude Code every day. Describe its behavior in terms of what you learned today.

Claude Code likely has tools for reading files, editing files, running terminal commands, and checking errors. It probably runs an agent loop where it decides which tool to use, observes the result, and continues until it can answer.

5. What could go wrong if an agent had the ability to DELETE books and there was no human-in-the-loop check?

The agent could delete the wrong book because of an unclear request. For example, “remove the George Orwell book” could match multiple books. A safer design would ask for confirmation before deleting.