import type { StudioPage } from "../types";

type Props = {
  page: StudioPage;
  onNavigate: (page: StudioPage) => void;
};

const items: { page: StudioPage; label: string; icon: string }[] = [
  { page: "home", label: "Home", icon: "⌂" },
  { page: "students", label: "Students", icon: "♙" },
  { page: "sessions", label: "Sessions", icon: "▣" },
  { page: "materials", label: "Materials", icon: "□" },
];

export function TopNav({ page, onNavigate }: Props) {
  const activePage = ["students", "sessions", "materials"].includes(page) ? page : "home";
  return (
    <header className="v2-topnav">
      <button className="v2-brand" onClick={() => onNavigate("home")} aria-label="Lesson Kit Studio home">
        <span className="v2-brand-mark" aria-hidden="true">▰</span>
        <span>Lesson Kit Studio</span>
      </button>
      <nav className="v2-mainnav" aria-label="Main navigation">
        {items.map((item) => (
          <button
            key={item.page}
            className={activePage === item.page ? "is-active" : ""}
            onClick={() => onNavigate(item.page)}
          >
            <span aria-hidden="true">{item.icon}</span>{item.label}
          </button>
        ))}
      </nav>
      <button className="v2-profile" aria-label="Teacher profile is not available in this demo" title="Profile menu is not available in this demo" disabled>
        <span className="v2-avatar">👩🏻</span><span aria-hidden="true">⌄</span>
      </button>
    </header>
  );
}
