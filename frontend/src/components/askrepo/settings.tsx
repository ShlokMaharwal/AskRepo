import { SlidersHorizontal } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";

export type SearchSettings = { hybrid: boolean; rerank: boolean; topK: number };

export function SearchSettingsDialog({
  value,
  onChange,
}: {
  value: SearchSettings;
  onChange: (value: SearchSettings) => void;
}) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button className="icon-button" aria-label="Search settings" title="Search settings">
          <SlidersHorizontal size={17} />
        </button>
      </DialogTrigger>
      <DialogContent className="ask-dialog">
        <DialogHeader>
          <DialogTitle>Retrieval settings</DialogTitle>
          <DialogDescription>Fine-tune how AskRepo searches your repository.</DialogDescription>
        </DialogHeader>
        <div className="setting-row">
          <label htmlFor="hybrid-search">
            <strong>Hybrid search</strong>
            <span>Combine keyword and semantic search with RRF.</span>
          </label>
          <Switch
            id="hybrid-search"
            checked={value.hybrid}
            onCheckedChange={(hybrid) => onChange({ ...value, hybrid })}
          />
        </div>
        <div className="setting-row">
          <label htmlFor="rerank-search">
            <strong>Reranker</strong>
            <span>Reorder results by relevance to your question.</span>
          </label>
          <Switch
            id="rerank-search"
            checked={value.rerank}
            onCheckedChange={(rerank) => onChange({ ...value, rerank })}
          />
        </div>
        <div className="setting-slider">
          <label id="top-k-label">
            Retrieved chunks <span>{value.topK}</span>
          </label>
          <Slider
            aria-labelledby="top-k-label"
            min={3}
            max={20}
            step={1}
            value={[value.topK]}
            onValueChange={([topK]) => onChange({ ...value, topK: topK ?? 8 })}
          />
          <div>
            <span>3 · focused</span>
            <span>20 · comprehensive</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
