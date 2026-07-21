"""Chess-style move grading — the ONLY grader in the codebase.

Contract 3: every move (AI or human) produces a MoveEvaluation
{from, to, grade, delta, note}, grade in
{Brilliant, Best, Good, Inaccuracy, Mistake, Blunder}.
`delta` is the change in estimated distance-to-target (semantic, per decision B).
Nothing else assigns grades; the UI only renders them.
"""
