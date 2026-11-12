import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it } from "vitest";
import { PageVisibility } from "../pageVisibility";
import { ProfilePortabilityDialog } from "./ProfilePortabilityDialog";

function Fixture({ visible = true }: { visible?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <PageVisibility value={visible}>
      <button onClick={() => setOpen(true)}>Export preferences</button>
      {open && (
        <ProfilePortabilityDialog
          mode="export"
          nativeRuntime={false}
          snapshotDigest={null}
          onClose={() => setOpen(false)}
          onComplete={() => undefined}
        />
      )}
    </PageVisibility>
  );
}

it("returns keyboard focus to the export opener after Escape", async () => {
  const user = userEvent.setup();
  render(<Fixture />);
  const opener = screen.getByRole("button", { name: "Export preferences" });
  await user.click(opener);
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(opener).toHaveFocus());
});

it("hides a retained page dialog without taking focus from the next page", async () => {
  const user = userEvent.setup();
  const { rerender } = render(
    <>
      <Fixture />
      <button>Next page</button>
    </>,
  );
  await user.click(screen.getByRole("button", { name: "Export preferences" }));
  rerender(
    <>
      <Fixture visible={false} />
      <button>Next page</button>
    </>,
  );
  screen.getByRole("button", { name: "Next page" }).focus();
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: "Next page" })).toHaveFocus();
});
