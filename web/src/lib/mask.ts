export function maskSender(sender?: string | null, channel?: string | null): string {
  if (!sender) return "—";
  const trimmed = sender.trim();
  if (channel === "whatsapp") {
    const base = trimmed.split("@")[0];
    const digits = base.replace(/\D/g, "");
    if (digits.length >= 4) {
      const last4 = digits.slice(-4);
      const prefix = digits.length > 4 ? `+${digits.slice(0, 2)} ` : "";
      return `${prefix}••••• •${last4}`;
    }
    if (base.length >= 4) {
      return `••••${base.slice(-4)}`;
    }
    return "••••";
  }
  const digits = trimmed.replace(/\D/g, "");
  if (digits.length >= 7 && !trimmed.includes("@")) {
    if (digits.length >= 4) {
      const last4 = digits.slice(-4);
      const prefix = digits.length > 4 ? `+${digits.slice(0, 2)} ` : "";
      return `${prefix}••••• •${last4}`;
    }
  }
  return trimmed;
}


