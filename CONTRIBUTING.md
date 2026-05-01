# Contributing to AI Stock Analyzer Desktop

First off, thank you for considering contributing to **AI Stock Analyzer Desktop**! It's people like you that make open-source tools great.

## 1. Where do I go from here?

If you've noticed a bug or have a feature request, make sure to check our [Issues](https://github.com/stratoslig/ai-stock-analyzer-Desktop/issues) page to see if someone else has already created a ticket. If not, go ahead and make one!

## 2. Fork & create a branch

If this is something you think you can fix, then fork AI Stock Analyzer Desktop and create a branch with a descriptive name.

```bash
git checkout -b fix/your-bug-name
# or
git checkout -b feature/your-feature-name
```

## 3. Implement your fix or feature

At this point, you're ready to make your changes. Feel free to ask for help; everyone is a beginner at first 😸.

**Coding Standards:**

- **Language:** Python 3.8+
- **UI Framework:** CustomTkinter. Try to follow the existing UI structure and Dark Theme patterns.
- **Translations:** If you are adding new UI text, please make sure to add it to BOTH dictionaries (`en` and `el`) inside `translations.py`.
- **Dependencies:** If you add a new library, remember to test if it supports *Lazy Loading* to maintain our instant startup time!

## 4. Test your changes

Make sure your changes do not break the existing application. Run `desktop_app.py` locally and verify that:

- The application starts instantly.
- API calls (Yahoo, Alpha Vantage, etc.) still work correctly.
- AI generation (Gemini or Ollama) formats the response properly.

## 5. Make a Pull Request (PR)

When you're done, push your branch to your fork and submit a Pull Request.

```bash
git push origin your-branch-name
```

Go to the repository on GitHub and click the **Compare & pull request** button.

### Pull Request Guidelines

- Keep your PRs small and focused on a single issue or feature.
- Add a descriptive title and explain what your PR solves.
- Mention if your PR closes an existing issue (e.g., `Closes #3`).

## 6. Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms. Be respectful, constructive, and kind!

---
Happy Coding! 🚀
