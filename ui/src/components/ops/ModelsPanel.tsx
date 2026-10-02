import { ModelRoleList } from "@/components/layout/ModelSettings"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useModels } from "@/hooks/useModels"

/** The model each agent runs on, straight on the agent server: the same
 *  setting as the dashboard's Models panel, used by the next run - including
 *  the one a page from here starts. */
export function ModelsPanel() {
  const { models, error, select } = useModels()
  return (
    <Card className="gap-4 py-4">
      <CardHeader className="px-4">
        <CardTitle className="text-sm">Models</CardTitle>
        <CardDescription className="text-xs">
          {models === null && error
            ? "Agent server not reachable."
            : "Used by the next run. Shared with every open dashboard."}
        </CardDescription>
      </CardHeader>
      <CardContent className="px-4">
        <ModelRoleList models={models} onSelect={select} />
      </CardContent>
    </Card>
  )
}
