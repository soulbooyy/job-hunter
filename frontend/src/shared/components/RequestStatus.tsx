export interface RequestStatusValue {
  tone: "progress" | "success" | "error";
  message: string;
}

interface RequestStatusProps {
  value: RequestStatusValue | null;
}

export function RequestStatus({ value }: RequestStatusProps) {
  if (value === null) {
    return <div className="request-status-placeholder" aria-live="polite" />;
  }

  return (
    <p
      className={`request-status request-status--${value.tone}`}
      role={value.tone === "error" ? "alert" : "status"}
    >
      {value.message}
    </p>
  );
}
