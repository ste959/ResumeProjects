import { Link } from 'react-router-dom';
import { ResearchLab } from './ResearchLab';

// The quant-research pipeline as its own self-contained app, under its own identity header. The
// Research Lab itself is backed by the FastAPI research service (/research-api).
export function ResearchApp() {
  return (
    <div className="app-shell research-shell">
      <header className="shell-head">
        <Link to="/" className="shell-back">← Projects</Link>
        <div className="shell-brand">
          <span className="shell-mark">∿</span>
          <div><h1>Quant Research</h1><p>leakage-free factor pipeline · honest overfitting stats</p></div>
        </div>
        <span className="shell-note">full write-up: research/RESEARCH-NOTE.md</span>
      </header>
      <ResearchLab />
    </div>
  );
}
