import { useMemo, useRef, useState } from "react";

import type { Entry } from "./types";

// A button that opens the model's current beliefs in a popup. Shown once there are any.
export function BeliefsPopup({ entries }: { entries: Entry[] }) {
  const beliefs = useMemo(() => allBeliefs(entries), [entries]);
  const dialog = useRef<HTMLDialogElement>(null);
  const [showDeleted, setShowDeleted] = useState(false);
  if (beliefs.size === 0) return null;
  const current = [...beliefs.values()].filter((belief) => !belief.dropped).length;
  return (
    <>
      <button type="button" className="beliefs-button" onClick={() => dialog.current!.showModal()}>
        Beliefs ({current})
      </button>
      {/* A click on the backdrop lands on the dialog itself, outside its content, and closes it. */}
      <dialog ref={dialog} className="beliefs" onClick={(event) => event.target === event.currentTarget && dialog.current!.close()}>
        <div>
          <header>
            <h2>What the model believes now</h2>
            <label>
              <input type="checkbox" checked={showDeleted} onChange={(event) => setShowDeleted(event.target.checked)} />
              Show deleted
            </label>
            <button type="button" onClick={() => dialog.current!.close()}>
              Close
            </button>
          </header>
          <ol>
            {[...beliefs].filter(([, { dropped }]) => showDeleted || !dropped).map(([number, { statement, dropped }]) => (
              <li key={number} value={Number(number)}>
                {dropped ? <del>{statement}</del> : statement}
              </li>
            ))}
          </ol>
        </div>
      </dialog>
    </>
  );
}

type Belief = { statement: string; dropped: boolean };

// Every belief the entries' revisions added, by number in the order added, and whether it was dropped since.
function allBeliefs(entries: Entry[]): Map<string, Belief> {
  const beliefs = new Map<string, Belief>();
  for (const entry of entries) {
    if (entry.kind !== "belief_revision") continue;
    for (const [number, statement] of Object.entries(entry.drop)) beliefs.set(number, { statement, dropped: true });
    for (const [number, statement] of Object.entries(entry.add)) beliefs.set(number, { statement, dropped: false });
  }
  return beliefs;
}
