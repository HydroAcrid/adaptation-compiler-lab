import * as Select from "@radix-ui/react-select";
import * as Switch from "@radix-ui/react-switch";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: "primary" | "secondary" | "quiet" | "danger";
  icon?: ReactNode;
}

export function Button({
  tone = "secondary",
  icon,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button className={`button button--${tone} ${className}`} {...props}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "positive" | "neutral" | "attention";
}) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

export function Toggle({
  checked,
  onCheckedChange,
  label,
  description,
  disabled = false,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <div className="toggle-row">
      <div className="toggle-copy">
        <span className="toggle-label">{label}</span>
        {description ? (
          <span className="toggle-description">{description}</span>
        ) : null}
      </div>
      <Switch.Root
        aria-label={label}
        checked={checked}
        className="switch-root"
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      >
        <Switch.Thumb className="switch-thumb" />
      </Switch.Root>
    </div>
  );
}

export interface TemperSelectOption<T extends string = string> {
  value: T;
  label: string;
  description?: string;
}

export function TemperSelect<T extends string>({
  ariaLabel,
  className = "",
  disabled = false,
  id,
  onValueChange,
  options,
  portalled = true,
  value,
}: {
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  id?: string;
  onValueChange: (value: T) => void;
  options: TemperSelectOption<T>[];
  portalled?: boolean;
  value: T;
}) {
  const content = (
    <Select.Content
      align="start"
      className="temper-select-content"
      collisionPadding={10}
      position="popper"
      sideOffset={6}
    >
      <Select.ScrollUpButton className="temper-select-scroll-button">
        <ChevronUp aria-hidden="true" size={14} />
      </Select.ScrollUpButton>
      <Select.Viewport className="temper-select-viewport">
        {options.map((option) => (
          <Select.Item
            className="temper-select-item"
            key={option.value}
            value={option.value}
          >
            <span className="temper-select-indicator">
              <Select.ItemIndicator>
                <Check aria-hidden="true" size={14} />
              </Select.ItemIndicator>
            </span>
            <span className="temper-select-option-copy">
              <Select.ItemText>{option.label}</Select.ItemText>
              {option.description ? <small>{option.description}</small> : null}
            </span>
          </Select.Item>
        ))}
      </Select.Viewport>
      <Select.ScrollDownButton className="temper-select-scroll-button">
        <ChevronDown aria-hidden="true" size={14} />
      </Select.ScrollDownButton>
    </Select.Content>
  );
  return (
    <Select.Root
      disabled={disabled}
      onValueChange={(nextValue) => onValueChange(nextValue as T)}
      value={value}
    >
      <Select.Trigger
        aria-label={ariaLabel}
        className={`temper-select-trigger ${className}`.trim()}
        id={id}
      >
        <Select.Value />
        <Select.Icon className="temper-select-chevron">
          <ChevronDown aria-hidden="true" size={14} strokeWidth={1.8} />
        </Select.Icon>
      </Select.Trigger>
      {portalled ? <Select.Portal>{content}</Select.Portal> : content}
    </Select.Root>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="section-heading">
      {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
    </div>
  );
}

export function Divider() {
  return <div aria-hidden="true" className="divider" />;
}
