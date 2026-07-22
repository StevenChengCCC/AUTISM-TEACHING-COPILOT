import type { StudioPage } from "../types";
import { useEffect,useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { BRAND } from "../brand";
import { BrandMark } from "./BrandMark";

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
  const { user, signOut } = useAuth();
  const [menuOpen,setMenuOpen]=useState(false);
  const [teachingMode,setTeachingMode]=useState(()=>sessionStorage.getItem("autism-teaching-copilot.teaching-mode")==="true");
  useEffect(()=>{document.body.classList.toggle("autism-copilot-teaching-mode",teachingMode);sessionStorage.setItem("autism-teaching-copilot.teaching-mode",String(teachingMode));return()=>document.body.classList.remove("autism-copilot-teaching-mode");},[teachingMode]);
  useEffect(()=>{if(!menuOpen)return;const close=(event:KeyboardEvent)=>{if(event.key==="Escape")setMenuOpen(false);};window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close);},[menuOpen]);
  const activePage = page === "developerAI" ? null : ["students", "sessions", "materials"].includes(page) ? page : "home";
  return (
    <header className="v2-topnav">
      <button className="v2-brand" onClick={() => onNavigate("home")} aria-label={`${BRAND.productName} home`} title={BRAND.productName}>
        <BrandMark />
        <span className="v2-brand-copy">
          <strong>{BRAND.productName}</strong>
          <small>{BRAND.descriptor}</small>
        </span>
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
      <div className="v2-nav-tools">
        <button className="v2-dev-link" aria-pressed={teachingMode} onClick={()=>setTeachingMode((value)=>!value)}>{teachingMode?"Exit teaching mode":"Teaching mode"}</button>
        {import.meta.env.DEV&&<button className={`v2-dev-link v2-ai-dev-link ${page==="developerAI"?"is-active":""}`} onClick={()=>onNavigate("developerAI")} title="Backend AI development checks">AI dev</button>}
        <button className="v2-profile" aria-label="Open teacher account menu" aria-expanded={menuOpen} aria-controls="teacher-account-menu" onClick={()=>setMenuOpen((value)=>!value)}>
          <span className="v2-avatar" aria-hidden="true">👩🏻</span><span className="v2-profile-name">{user?.displayName ?? "Teacher"}</span><span aria-hidden="true">⌄</span>
        </button>
        {menuOpen&&<div className="v2-account-menu" id="teacher-account-menu" role="menu">
          <strong>{user?.displayName ?? "Teacher"}</strong>
          {user?.email&&<span>{user.email}</span>}
          <button role="menuitem" onClick={signOut}>Sign out</button>
        </div>}
      </div>
    </header>
  );
}
