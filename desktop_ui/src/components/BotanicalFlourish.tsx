export function BotanicalFlourish({
  placement,
}: {
  placement: "workspace" | "onboarding";
}) {
  return (
    <span
      aria-hidden="true"
      className={`botanical-flourish botanical-flourish--${placement}`}
    />
  );
}
