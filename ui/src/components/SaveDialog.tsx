import { useEffect, useState } from "react";

interface Props {
  open: boolean;
  title: string;
  hint: string;
  defaultName: string;
  busy: boolean;
  onClose: () => void;
  onSave: (name: string) => void;
}

export default function SaveDialog({
  open,
  title,
  hint,
  defaultName,
  busy,
  onClose,
  onSave,
}: Props) {
  const [name, setName] = useState(defaultName);

  useEffect(() => {
    if (open) setName(defaultName);
  }, [open, defaultName]);

  if (!open) return null;

  const submit = () => {
    const cleaned = name.trim();
    if (cleaned && !busy) onSave(cleaned);
  };

  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div
        className="modal save-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            <p className="hint">{hint}</p>
          </div>
        </div>
        <div className="save-form">
          <label className="field">
            <span className="field-label">Name</span>
            <input
              autoFocus
              type="text"
              maxLength={80}
              value={name}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submit();
                }
                if (event.key === "Escape") onClose();
              }}
            />
          </label>
          <p className="hint">
            Saving with an existing name updates that saved design instead of adding a duplicate.
          </p>
          <div className="save-actions">
            <button type="button" className="button-quiet" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              type="button"
              className="button-primary"
              onClick={submit}
              disabled={busy || !name.trim()}
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
