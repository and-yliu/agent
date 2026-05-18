from dataclasses import dataclass 
import re
from pathlib import Path

@dataclass
class SkillManifest:
    name: str
    description: str

@dataclass
class SkillDocument:
    manifest: SkillManifest
    body: str

class SkillRegistry:
    def __init__(self, skill_dir: Path):
        self.path = skill_dir
        self.skills: dict[str, SkillDocument] = {}
        self._load_all()
    
    def _load_all(self):
        for path in self.path.rglob("SKILL.md"):
            meta, body = self._parse_frontmatter(path.read_text())
            name = meta.get("name", path.parent.name)
            self.skills[name] = SkillDocument(SkillManifest(name, meta.get("description", "")), body)
    
    def _parse_frontmatter(self, body: str) -> tuple[dict, str]:
        match = re.match("^---\n(.*?)\n---\n(.*)", body, re.DOTALL)
        if not match:
            return {}, body

        meta = {}
        for line in match.group(1).strip().splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
        
        return meta, match.group(2).strip()

    
    def describe_available(self) -> str:
        if not self.skills:
            return "(no skills available)"
        lines = []
        for name in sorted(self.skills):
            manifest = self.skills[name].manifest
            lines.append(f"- {manifest.name}: {manifest.description}")
        return "\n".join(lines)

    def load_skill(self, name: str) -> str:
        skill = self.skills.get(name)
        if not skill:
            return f"Error: Unknown skill {name}. Available skills: {self.skills.keys()}"
        
        return (
            f"<skill name=\"{skill.manifest.name}\">\n"
            f"{skill.body}\n"
            "</skill>"
        )
