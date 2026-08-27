import httpx
import pytest
from playwright.async_api import Page, Route, expect

pytestmark = pytest.mark.asyncio(loop_scope="session")

async def test_adding_a_student_shows_it_in_the_list_and_the_session_picker(
        dashboard_page: Page,
        auth_client: httpx.AsyncClient,
        unique_name: str,  
) -> None:

    """create-form -> api.createStudent -> studensts.refresh() re-renders both 
    #student-list and #active-student from the same response, so this checks 
    # both instead of just the list
    
    """
    await dashboard_page.get_by_placeholder("New student name").fill(unique_name)
    await dashboard_page.get_by_role("button", name="Add").click()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    await expect(row).to_be_visible
    await expect(row.locator(".s-points")).to_have_text("0 pts")

    await expect(dashboard_page.locator("#active-student option", has_text=unique_name)).to_have_count(1)