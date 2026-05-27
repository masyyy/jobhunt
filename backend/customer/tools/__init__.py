from backend.core.agents.config import AgentConfig
from backend.core.tools.execute_sql import execute_sql
from backend.core.tools.read_file import list_files, read_file
from backend.core.tools.search_files import search_files
from backend.customer.toolboxes import Toolbox

TOOLBOX_AGENT_CONFIG: dict[Toolbox, AgentConfig] = {
    Toolbox.SALES: AgentConfig(
        tools=[execute_sql, read_file, list_files, search_files],
    ),
    Toolbox.PRODUCTION: AgentConfig(
        tools=[execute_sql, read_file, list_files, search_files],
    ),
}
