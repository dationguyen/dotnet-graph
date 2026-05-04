using SampleSolution.Core.Services;

namespace SampleSolution.Core.ViewModels;

public class UserViewModel
{
    private readonly IUserService _userService;

    public UserViewModel(IUserService userService)
    {
        _userService = userService;
    }

    public string Title { get; set; } = "Users";
    public bool IsLoading { get; set; }

    public async Task LoadAsync()
    {
        IsLoading = true;
        var users = await _userService.ListUsersAsync();
        IsLoading = false;
    }

    public async Task CreateUserAsync(string name, string email)
    {
        await _userService.CreateUserAsync(name, email);
        await LoadAsync();
    }
}
