"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Folder, Plus, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { tasksApi } from "@/lib/api"
import type { Task } from "@/types/api"

interface DataroomSidebarProps {
  datarooms: Task[]
  selectedId: string | null
  onSelect: (id: string) => void
  onRefresh: () => void
}

export function DataroomSidebar({ datarooms, selectedId, onSelect, onRefresh }: DataroomSidebarProps) {
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [newTaskName, setNewTaskName] = useState("")
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreateTask = async () => {
    if (!newTaskName.trim()) return

    setIsCreating(true)
    setError(null)

    try {
      await tasksApi.create({ name: newTaskName.trim() })
      setNewTaskName("")
      setShowNewDialog(false)
      onRefresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task")
    } finally {
      setIsCreating(false)
    }
  }

  const getRiskBadge = (riskLevel: Task["risk_level"]) => {
    if (riskLevel === "risky") return "🚩"
    if (riskLevel === "healthy") return "✅"
    return ""
  }

  return (
    <div className="w-80 border-r border-border bg-card flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-foreground">RIGOR</h1>
        </div>
        <Button className="w-full" size="sm" onClick={() => setShowNewDialog(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Dataroom
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-1">
          <div className="px-3 py-2">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Datarooms</h2>
          </div>
          {datarooms.map((dataroom) => (
            <button
              key={dataroom.id}
              onClick={() => onSelect(dataroom.id)}
              className={cn(
                "w-full text-left px-3 py-2.5 rounded-md transition-colors",
                "hover:bg-accent",
                selectedId === dataroom.id && "bg-accent",
              )}
            >
              <div className="flex items-start gap-3">
                <Folder className="w-5 h-5 mt-0.5 text-primary flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm text-foreground truncate flex items-center gap-2">
                    {dataroom.name}
                    <span>{getRiskBadge(dataroom.risk_level)}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {new Date(dataroom.created_at).toLocaleDateString()}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>

      <Dialog open={showNewDialog} onOpenChange={setShowNewDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Dataroom</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Input
                placeholder="Enter deal name (e.g., Microsoft Acquisition)"
                value={newTaskName}
                onChange={(e) => setNewTaskName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateTask()}
              />
            </div>
            {error && (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewDialog(false)} disabled={isCreating}>
              Cancel
            </Button>
            <Button onClick={handleCreateTask} disabled={isCreating || !newTaskName.trim()}>
              {isCreating ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
