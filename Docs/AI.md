# Main Purpose
Relentlessly update and add onto this .md file after making mistakes or when you have done something good and I want you to keep doing that thing. 
This is from Boris Cherny, the creator of Claude code, he said:
I'm Boris and I created Claude Code. I wanted to quickly share a few tips for using Claude Code, sourced directly from the Claude Code team. The way the team uses Claude is different than how I use it. Remember: there is no one right way to use Claude Code -- everyones' setup is different. You should experiment to see what works for you!

### AI Tips
set up 3-5 git worktrees all at the same time
start every complex task in plan mode and really work on the plan so claude 1-shots the implementation
use claude.md and update it everytime it makes a mistake
create your own skills and commit them to git
	-turn repetitive things into /commands
	-/techdebt command and run at every session to find and kill duplicate code
	-/ command that syncs 7 days of Slack, GDrive, Asana, and GitHub into one context dump
	- Build analytics-engineer-style agents that write dbt models, review code, and test changes in dev


## claude tips
1. Do more in parallel

Spin up 3–5 git worktrees at once, each running its own Claude session in parallel. It's the single biggest productivity unlock, and the top tip from the team. Personally, I use multiple git checkouts, but most of the Claude Code team prefers worktrees -- it's the reason 

 built native support for them into the Claude Desktop app!

Some people also name their worktrees and set up shell aliases (za, zb, zc) so they can hop between them in one keystroke. Others have a dedicated "analysis" worktree that's only for reading logs and running BigQuery

2. Start every complex task in plan mode. Pour your energy into the plan so Claude can 1-shot the implementation.

One person has one Claude write the plan, then they spin up a second Claude to review it as a staff engineer. 

Another says the moment something goes sideways, they switch back to plan mode and re-plan. Don't keep pushing. They also explicitly tell Claude to enter plan mode for verification steps, not just for the build

3. Invest in your http://CLAUDE.md. After every correction, end with: "Update your http://CLAUDE.md so you don't make that mistake again." Claude is eerily good at writing rules for itself.

Ruthlessly edit your http://CLAUDE.md over time. Keep iterating until Claude's mistake rate measurably drops.

One engineer tells Claude to maintain a notes directory for every task/project, updated after every PR. They then point http://CLAUDE.md at it.

4. Create your own skills and commit them to git. Reuse across every project.

Tips from the team:
- If you do something more than once a day, turn it into a skill or command
- Build a /techdebt slash command and run it at the end of every session to find and kill duplicated code
- Set up a slash command that syncs 7 days of Slack, GDrive, Asana, and GitHub into one context dump
- Build analytics-engineer-style agents that write dbt models, review code, and test changes in dev

5. Claude fixes most bugs by itself. Here's how we do it:

Enable the Slack MCP, then paste a Slack bug thread into Claude and just say "fix." Zero context switching required.

Or, just say "Go fix the failing CI tests." Don't micromanage how.

Point Claude at docker logs to troubleshoot distributed systems -- it's surprisingly capable at this.

6. Level up your prompting

a. Challenge Claude. Say "Grill me on these changes and don't make a PR until I pass your test." Make Claude be your reviewer.  Or, say "Prove to me this works" and have Claude diff behavior between main and your feature branch

b. After a mediocre fix, say: "Knowing everything you know now, scrap this and implement the elegant solution"

c. Write detailed specs and reduce ambiguity before handing work off. The more specific you are, the better the output

. Terminal & Environment Setup

The team loves Ghostty! Multiple people like its synchronized rendering, 24-bit color, and proper unicode support.

For easier Claude-juggling, use /statusline to customize your status bar to always show context usage and current git branch. Many of us also color-code and name our terminal tabs, sometimes using tmux — one tab per task/worktree. 

Use voice dictation. You speak 3x faster than you type, and your prompts get way more detailed as a result. (hit fn x2 on macOS)

More tips: https://code.claude.com/docs/en/terminal-config

8. Use subagents

a. Append "use subagents" to any request where you want Claude to throw more compute at the problem

b. Offload individual tasks to subagents to keep your main agent's context window clean and focused

c. Route permission requests to Opus 4.5 via a hook — let it scan for attacks and auto-approve the safe ones (see https://code.claude.com/docs/en/hooks#permissionrequest)

9. Use Claude for data & analytics

Ask Claude Code to use the "bq" CLI to pull and analyze metrics on the fly. We have a BigQuery skill checked into the codebase, and everyone on the team uses it for anlytics queries directly in Claude Code. Personally, I haven't written a line of SQL in 6+ months.

This works for any database that has a CLI, MCP, or API.

10. Learning with Claude

A few tips from the team to use Claude Code for learning:

a. Enable the "Explanatory" or "Learning" output style in /config to have Claude explain the *why* behind its changes

b. Have Claude generate a visual HTML presentation explaining unfamiliar code. It makes surprisingly good slides!

c. Ask Claude to draw ASCII diagrams of new protocols and codebases to help you understand them

d. Build a spaced-repetition learning skill: you explain your understanding, Claude asks follow-ups to fill gaps, stores the result


## claude plan mode
Claude Code Prompt for Plan Mode

Review this plan thoroughly before making any code changes. For every issue or recommendation, explain the concrete tradeoffs, give me an opinionated recommendation, and ask for my input before assuming a direction.

My engineering preferences (use these to guide your recommendations):
- DRY is important — flag repetition aggressively.
- Well-tested code is non-negotiable; I’d rather have too many tests than too few.
- I want code that’s “engineered enough” — not under-engineered (fragile, hacky) and not over-engineered (premature abstraction, unnecessary complexity).
- I err on the side of handling more edge cases, not fewer.
- Bias toward explicit over clever.

Architecture review  
Evaluate:
- Overall system design and component boundaries.
- Dependency graph and coupling concerns.
- Data flow patterns and potential bottlenecks.
- Scaling characteristics and single points of failure.
- Security architecture (auth, data access, API boundaries).

2. Code quality review  
Evaluate:
- Code organization and module structure.
- DRY violations — be aggressive here.
- Error handling patterns and missing edge cases (call these out explicitly).
- Technical debt hotspots.
- Areas that are over-engineered or under-engineered relative to my preferences.

3. Test review  
Evaluate:
- Test coverage gaps (unit, integration, e2e).
- Test quality and assertion strength.
- Missing edge case coverage — be thorough.
- Untested failure modes and error paths.

4. Performance review  
Evaluate:
- N+1 queries and database access patterns.
- Memory usage concerns.
- Caching opportunities.
- Slow or high-complexity code paths.

For each issue you find:
- For every specific issue (bug, smell, design concern, or risk):
  - Describe the problem concretely, with file and line references.
  - Present 2–3 options, including “do nothing” where reasonable.
  - For each option, specify implementation effort, risk, impact on other code, and maintenance burden.
  - Give me your recommended option and why, mapped to my preferences above.
  - Then explicitly ask whether I agree or want to choose a different direction before proceeding.

Workflow and interaction:
- Do not assume my priorities on timeline or scope.
- After each section, pause and ask for my feedback before moving on.

BEFORE YOU START:
Ask if I want one of two options:

1) BIG CHANGE: Work through this interactively, one section at a time (Architecture → Code Quality → Tests → Performance) with at most 4 top issues in each section.

2) SMALL CHANGE: Work through interactively ONE question per review section.

FOR EACH STAGE OF REVIEW:
- Output the explanation and pros and cons of each stage’s questions AND your opinionated recommendation and why.
- Then use AskUserQuestion.
- Also NUMBER issues and then give LETTERS for options.
- When using AskUserQuestion, make sure each option clearly labels the issue NUMBER and option LETTER so the user doesn’t get confused.
- Make the recommended option always the first option.
