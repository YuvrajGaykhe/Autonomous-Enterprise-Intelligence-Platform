/**
 * What the canvas shows beyond the agents, in text (spec §10): SIGNALS_AGENT's board and the
 * CEO's corkboard. Screen readers read it; it is visually hidden, since the canvas draws it.
 */

import type { BoardState, CorkNote } from './worldTypes';

const BOARD_WORDS: Readonly<Record<Exclude<BoardState['kind'], 'ready'>, string>> = {
  loading: 'The board is loading.',
  empty: 'The board is blank: no brief is selected at this date.',
  error: 'The board is blank: its assessment could not be read.',
};

export function OfficeText({ board, notes }: { board: BoardState; notes: readonly CorkNote[] }) {
  return (
    <div className="sr-only">
      <section aria-label="SIGNALS_AGENT's board">
        {board.kind === 'ready' ? (
          <>
            <p>{board.board.title}</p>
            <ul>
              {board.board.cells.map((cell) => (
                <li key={cell.id}>
                  {cell.id} {cell.key}: {cell.value}
                </li>
              ))}
            </ul>
            <p>{board.board.footer}</p>
          </>
        ) : (
          <p>{BOARD_WORDS[board.kind]}</p>
        )}
      </section>
      <section aria-label="The CEO's corkboard">
        {notes.length === 0 ? (
          <p>No decision is pinned for the selected brief.</p>
        ) : (
          <ol>
            {notes.map((note) => (
              <li key={note.ordinal}>
                Decision {note.ordinal}: {note.decision}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
