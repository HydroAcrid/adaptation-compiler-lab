export function BotanicalFlourish({
  placement,
}: {
  placement: "workspace" | "onboarding";
}) {
  return (
    <svg
      aria-hidden="true"
      className={`botanical-flourish botanical-flourish--${placement}`}
      fill="none"
      focusable="false"
      viewBox="0 0 620 250"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      >
        <path d="M618 28c-69-8-98 35-158 31-72-5-87 54-151 49-65-5-75 48-133 45-55-3-80-41-67-76 9-25 37-28 48-10 12 20-9 41-27 30" />
        <path d="M495 59c-22 9-26 30-18 43 10 17 38 12 36-8-1-13-17-18-27-8" />
        <path d="M371 91c-16-20-44-21-61-6-15 14-13 39 7 45 15 5 30-9 24-23-4-10-17-11-23-4" />
        <path d="M242 133c-21 4-35 20-35 40 0 22 22 34 39 24 13-8 12-28-2-33-10-4-19 5-16 14" />
        <path d="M111 113c-27 15-47 39-52 69-5 28 8 53 33 57" />
        <path d="M91 146c-23-2-39 10-42 26" />
        <path d="M453 59c-2-26 14-43 36-47" />
        <path d="M309 108c-8 24-27 38-50 40" />
        <path d="M176 153c-6 23-21 38-43 45" />
      </g>

      <g fill="currentColor">
        <path d="M514 48c18-19 39-22 55-13-5 20-24 32-55 13Z" opacity=".58" />
        <path d="M446 58c-20-14-27-32-21-49 20 2 34 20 21 49Z" opacity=".42" />
        <path d="M390 82c20-15 40-17 55-5-8 19-28 27-55 5Z" opacity=".58" />
        <path d="M303 108c-19-16-24-35-15-51 20 5 31 25 15 51Z" opacity=".45" />
        <path d="M256 146c18-14 37-16 52-5-8 18-26 25-52 5Z" opacity=".58" />
        <path d="M174 152c-18-16-22-34-13-49 19 6 29 25 13 49Z" opacity=".43" />
        <path d="M126 188c19-8 36-5 46 8-11 14-29 17-46-8Z" opacity=".56" />
        <path d="M59 182c-17-12-22-28-15-42 17 3 28 19 15 42Z" opacity=".43" />
      </g>

      <g fill="currentColor" opacity=".6">
        <circle cx="574" cy="32" r="3.5" />
        <circle cx="548" cy="41" r="2.2" />
        <circle cx="439" cy="66" r="2.6" />
        <circle cx="281" cy="127" r="2.8" />
        <circle cx="101" cy="214" r="3.2" />
      </g>
    </svg>
  );
}
