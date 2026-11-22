// Cut down from the game repo's Assets/Scripts/UI/UiController.cs at #4052's merge base (w5096 fixture): the comment
// that quotes Ben's w2097 rule, and CloseAllPanels, which it names and #4052 changed.
namespace FinalFactory.UI
{
  public partial class UiController
  {
    private void HandleSelectionChangedEvent(Entity selectedEntity)
    {
      if (selectedEntity != Entity.Null)
      {
        OnCloseActivePanels?.Invoke();
        // w2097 (Ben: "if you have inventory/craft panel opened and select something, it will close the
        // inventory/craft panel to show the structure UI, and vice versa"): a selection closes Inventory and Crafting,
        // as E closes the selection's windows (HandleInventoryTogglePressed, CloseAllPanels). They stayed open before,
        // under or over the building's windows, whose labels read through them.
        if (IsInventoryPanelOpen)
        {
          ShowPlayerWindows(false);
        }

        OnEntitySelected?.Invoke(selectedEntity);
      }
    }

    private void Unrelated()
    {
      var a = 1;
      var b = 2;
      var c = 3;
      var d = 4;
      var e = 5;
      var f = 6;
    }

    public static bool CloseAllPanels()
    {
      return ProtectedInstance.CloseAllPanelsImpl();
    }

    private bool CloseAllPanelsImpl()
    {
      ShowMiniInventoryPanel(false);
      if (IsModulePanelOpen)
      {
        MouseRaycastSystem.Instance.Deselect();
        return true;
      }

      return false;
    }

    public void Update()
    {
      Tick();
    }
  }
}
