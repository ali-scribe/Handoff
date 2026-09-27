/** Small inline loading indicator with an accessible label. */
interface SpinnerProps {
  label?: string;
}

function Spinner({ label = "Loading…" }: SpinnerProps) {
  return (
    <span className="spinner" role="status" aria-live="polite">
      {label}
    </span>
  );
}

export default Spinner;
